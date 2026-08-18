#!/bin/bash
# =============================================================================
# isolate-engine-v2.sh — non-destructive policy engine isolation
# =============================================================================
#
# WHY THIS REPLACES isolate-engine.sh
# -----------------------------------
# The original script DELETED ValidatingWebhookConfiguration objects:
#
#     kubectl delete validatingwebhookconfigurations \
#       gatekeeper-validating-webhook-configuration
#
# Kyverno rebuilds its own webhooks on controller startup, so for Kyverno this
# looked like it worked. Gatekeeper does NOT: its webhook is a static artefact
# installed by the Helm chart. Once deleted, scaling the pods back up never
# restores it.
#
# Consequence, confirmed forensically: the webhook was destroyed at 13:13:48 on
# 26 July — one second after benchmark-baseline-20260726-131347.csv began. Every
# Gatekeeper measurement taken after that point was recorded against an engine
# that was scaled up, reporting healthy, and completely disconnected from the
# admission path. Ten hours of data, silently void. No error, no log entry.
#
# HOW THIS VERSION WORKS
# ----------------------
# Nothing is deleted. Each webhook's objectSelector is patched to require a
# label that no object in the cluster carries, so the API server skips calling
# it. The webhook object, its rules, and critically its TLS caBundle all stay
# intact. Restoring is a patch, not a reinstall.
#
# objectSelector rather than namespaceSelector on purpose: namespaceSelector has
# no effect on cluster-scoped resources, so ClusterRole, ClusterRoleBinding and
# Namespace policies (REQ-003, REQ-004, REQ-028) would keep firing. objectSelector
# filters on the object's own labels and applies to both scopes.
#
# Café analogy: the old script fired the inspector and hoped a new one would
# turn up. Kyverno's agency sends a replacement automatically; Gatekeeper's does
# not, so that counter went uninspected for ten hours while the rota still
# showed someone on duty. This version leaves the inspector employed and just
# changes which deliveries get routed past their desk.
#
# POD REPLICAS ARE LEFT ALONE — deliberately
# ------------------------------------------
# The original scaled controller pods to zero, which changes the machine's
# resource baseline between configurations. That is a second confound on top of
# the run-order one, and it inflates whichever configuration happens to run with
# fewer pods alive. Here both engines keep running and only the admission path
# changes, so the comparison isolates admission cost specifically.
# Pass --scale-pods if you want the old behaviour for a controller-overhead
# measurement, but do not mix the two in one dataset.
#
# USAGE
#   ./isolate-engine-v2.sh baseline      # neither engine validates
#   ./isolate-engine-v2.sh kyverno       # Kyverno only
#   ./isolate-engine-v2.sh gatekeeper    # Gatekeeper only
#   ./isolate-engine-v2.sh both          # restore full enforcement
#   ./isolate-engine-v2.sh status        # show current state
#   ./isolate-engine-v2.sh verify        # prove the isolation actually holds
# =============================================================================

set -uo pipefail    # -e omitted: the original died silently on empty greps

MODE="${1:-status}"
SCALE_PODS="${SCALE_PODS:-false}"
[ "${2:-}" = "--scale-pods" ] && SCALE_PODS=true

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="$SCRIPT_DIR/../evidence/webhook-state"
SENTINEL_KEY="dora-isolation/disabled"
SENTINEL_VAL="true"

mkdir -p "$STATE_DIR"

GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${GREEN}[✓]${NC} $1"; }
info() { echo -e "${BLUE}[i]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; }

KYVERNO_WH=(
  kyverno-resource-validating-webhook-cfg
  kyverno-policy-validating-webhook-cfg
  kyverno-exception-validating-webhook-cfg
  kyverno-cel-exception-validating-webhook-cfg
  kyverno-global-context-validating-webhook-cfg
  kyverno-cleanup-validating-webhook-cfg
  kyverno-ttl-validating-webhook-cfg
)
GATEKEEPER_WH=(gatekeeper-validating-webhook-configuration)

# --- one-time pristine backup -------------------------------------------------
# Taken once and never overwritten. The original script re-backed-up on every
# run, so by the time anyone looked, the "backup" recorded the broken state:
# all-webhooks-20260817-082848.yaml was 5.5KB SMALLER than the July copy because
# the Gatekeeper webhook was already gone.
snapshot_once() {
    local f="$STATE_DIR/pristine-webhooks.yaml"
    if [ -f "$f" ]; then
        info "Pristine snapshot already exists (not overwriting): $f"
        return
    fi
    kubectl get validatingwebhookconfigurations -o yaml > "$f" 2>/dev/null || true
    local n
    n=$(grep -c "^  - name:" "$f" 2>/dev/null || echo 0)
    if [ "$n" -lt 5 ]; then
        warn "Snapshot contains only $n webhooks — cluster may already be degraded."
        warn "Restore from evidence/forensics/ before trusting this snapshot."
    fi
    log "Pristine snapshot saved: $f"
}

# --- webhook enable / disable --------------------------------------------------
set_webhook_state() {
    local cfg="$1" action="$2"   # action = disable | enable
    kubectl get validatingwebhookconfiguration "$cfg" >/dev/null 2>&1 || {
        warn "$cfg not present — skipping"
        return
    }

    local count
    count=$(kubectl get validatingwebhookconfiguration "$cfg" \
            -o jsonpath='{.webhooks[*].name}' 2>/dev/null | wc -w)
    [ "$count" -eq 0 ] && { warn "$cfg has no webhooks"; return; }

    local patch i=0
    patch="["
    while [ "$i" -lt "$count" ]; do
        [ "$i" -gt 0 ] && patch="$patch,"
        if [ "$action" = "disable" ]; then
            patch="$patch{\"op\":\"replace\",\"path\":\"/webhooks/$i/objectSelector\",\"value\":{\"matchLabels\":{\"$SENTINEL_KEY\":\"$SENTINEL_VAL\"}}}"
        else
            # Empty selector = match everything, which is the default behaviour.
            patch="$patch{\"op\":\"replace\",\"path\":\"/webhooks/$i/objectSelector\",\"value\":{}}"
        fi
        i=$((i + 1))
    done
    patch="$patch]"

    kubectl patch validatingwebhookconfiguration "$cfg" \
        --type=json -p "$patch" >/dev/null 2>&1 \
        && echo "      $cfg ($count webhook(s)) -> $action" \
        || warn "failed to $action $cfg"
}

apply_to_group() {
    local action="$1"; shift
    for cfg in "$@"; do set_webhook_state "$cfg" "$action"; done
}

scale_engine() {
    [ "$SCALE_PODS" != "true" ] && return
    local ns="$1" replicas="$2"
    warn "Scaling $ns to $replicas — this changes the resource baseline"
    kubectl scale deployment -n "$ns" --all --replicas="$replicas" >/dev/null 2>&1 || true
    [ "$replicas" -gt 0 ] && kubectl wait --for=condition=ready pod --all -n "$ns" --timeout=180s >/dev/null 2>&1 || true
}

# --- reporting ----------------------------------------------------------------
show_status() {
    echo ""
    echo "=== Engine Status ==="
    printf "%-52s %-10s %s\n" "WEBHOOK CONFIG" "WEBHOOKS" "STATE"
    printf '%.0s-' {1..78}; echo
    for cfg in "${KYVERNO_WH[@]}" "${GATEKEEPER_WH[@]}"; do
        if ! kubectl get validatingwebhookconfiguration "$cfg" >/dev/null 2>&1; then
            printf "%-52s %-10s ${RED}%s${NC}\n" "$cfg" "-" "ABSENT"
            continue
        fi
        local n sel state
        n=$(kubectl get validatingwebhookconfiguration "$cfg" -o jsonpath='{.webhooks[*].name}' 2>/dev/null | wc -w)
        sel=$(kubectl get validatingwebhookconfiguration "$cfg" -o jsonpath="{.webhooks[0].objectSelector.matchLabels['dora-isolation/disabled']}" 2>/dev/null)
        if [ "$sel" = "$SENTINEL_VAL" ]; then state="disabled"; else state="ACTIVE"; fi
        printf "%-52s %-10s %s\n" "$cfg" "$n" "$state"
    done
    echo ""
    echo "Controller pods:"
    kubectl get pods -n kyverno --no-headers 2>/dev/null | awk '{printf "   %-52s %s\n",$1,$3}'
    kubectl get pods -n gatekeeper-system --no-headers 2>/dev/null | awk '{printf "   %-52s %s\n",$1,$3}'
    echo ""
}

# Behavioural proof. Status fields lie: on 26 July both engines reported healthy
# pods and active constraints while Gatekeeper had no webhook at all. The only
# trustworthy check is whether a known-bad manifest is actually refused.
verify_isolation() {
    local probe="$SCRIPT_DIR/../manifests/non-compliant/req010-violation.yaml"
    [ -f "$probe" ] || { err "probe manifest missing: $probe"; return 1; }

    echo ""
    info "Behavioural check with manifests/non-compliant/req010-violation.yaml"
    local out
    out=$(kubectl apply --dry-run=server -f "$probe" 2>&1)

    if echo "$out" | grep -q "dry run"; then
        echo "   RESULT: ADMITTED — no engine is validating this path"
    elif echo "$out" | grep -q "kyverno"; then
        echo "   RESULT: DENIED by Kyverno"
    elif echo "$out" | grep -q "gatekeeper"; then
        echo "   RESULT: DENIED by Gatekeeper"
    else
        echo "   RESULT: DENIED by something else — inspect manually:"
        echo "$out" | head -5
    fi

    case "$MODE" in
        baseline)   echo "   EXPECTED for '$MODE': ADMITTED" ;;
        kyverno)    echo "   EXPECTED for '$MODE': DENIED by Kyverno" ;;
        gatekeeper) echo "   EXPECTED for '$MODE': DENIED by Gatekeeper" ;;
        both)       echo "   EXPECTED for '$MODE': DENIED (either engine)" ;;
    esac
    echo ""
    warn "If the result does not match, the measurement that follows is invalid."
}

# --- main ---------------------------------------------------------------------
case "$MODE" in
    baseline)
        echo "=== Isolating: BASELINE (no validation) ==="
        snapshot_once
        info "Disabling Kyverno webhooks..."   ; apply_to_group disable "${KYVERNO_WH[@]}"
        info "Disabling Gatekeeper webhooks..."; apply_to_group disable "${GATEKEEPER_WH[@]}"
        scale_engine kyverno 0; scale_engine gatekeeper-system 0
        log "Baseline ready"; show_status; verify_isolation
        ;;
    kyverno)
        echo "=== Isolating: KYVERNO ONLY ==="
        snapshot_once
        info "Enabling Kyverno webhooks..."    ; apply_to_group enable  "${KYVERNO_WH[@]}"
        info "Disabling Gatekeeper webhooks..."; apply_to_group disable "${GATEKEEPER_WH[@]}"
        scale_engine kyverno 1
        log "Kyverno isolated"; show_status; verify_isolation
        ;;
    gatekeeper)
        echo "=== Isolating: GATEKEEPER ONLY ==="
        snapshot_once
        info "Disabling Kyverno webhooks..."  ; apply_to_group disable "${KYVERNO_WH[@]}"
        info "Enabling Gatekeeper webhooks..."; apply_to_group enable  "${GATEKEEPER_WH[@]}"
        scale_engine gatekeeper-system 1
        log "Gatekeeper isolated"; show_status; verify_isolation
        ;;
    both|restore)
        echo "=== Restoring: BOTH ENGINES ==="
        info "Enabling all webhooks..."
        apply_to_group enable "${KYVERNO_WH[@]}" "${GATEKEEPER_WH[@]}"
        scale_engine kyverno 1; scale_engine gatekeeper-system 1
        log "Both engines enforcing"; show_status
        ;;
    status)
        show_status
        ;;
    verify)
        verify_isolation
        ;;
    *)
        echo "Usage: $0 {baseline|kyverno|gatekeeper|both|status|verify} [--scale-pods]"
        exit 1
        ;;
esac
