#!/bin/bash
# =============================================================================
# benchmark-rcbd.sh (v3) — CA2-aligned, randomised complete block design
# =============================================================================
#
# ALIGNMENT WITH THE CA2 PROPOSAL
# --------------------------------
# CA2 specified: "The time overhead each tool adds to ArgoCD sync operations
# will be measured. Fifty sync cycles will be executed for each of three
# configurations; baseline (no policy engine), Kyverno, and OPA Gatekeeper,
# using the same set of manifests. Mean sync duration and standard deviation
# will be compared across the three conditions."
#
# This script implements exactly that, with one deliberate methodological
# correction:
#
#   CA2 element                     | Implementation
#   --------------------------------|--------------------------------------
#   ArgoCD sync operations          | primary metric argocd_sync_ms
#   50 cycles per configuration     | 10 blocks x 5 reps = 50
#   baseline = NO policy engine     | controllers scaled to 0 replicas
#   same manifests across configs   | dora-bench-compliant (compliant only)
#   mean and standard deviation     | reported, alongside non-parametric tests
#   CORRECTION: cycle ordering      | randomised blocks, not sequential runs
#
# WHY THE ORDERING CORRECTION IS NECESSARY
# ----------------------------------------
# CA2 implied sequential execution (all baseline, then Kyverno, then Gatekeeper).
# The 26 July run did exactly that and produced an impossible result: the
# baseline was SLOWER than running with an admission webhook. Diagnostics showed
# Spearman rho = -0.85 (p ~ 1e-14) between cycle index and duration within the
# Kyverno block, and mean 1-minute load of 3.14 during baseline versus 1.42
# during Kyverno. Configuration was confounded with time and system load.
#
# Randomised blocking measures every configuration once inside every block, in
# an order reshuffled per block, so drift affects all three roughly equally.
# This is a strengthening of the CA2 design, not a departure from it, and should
# be presented that way in Chapter 3.
#
# TRUE BASELINE — why controllers are scaled to zero
# --------------------------------------------------
# "No policy engine" means the controllers are not running. Leaving them
# resident and merely disabling enforcement would measure the enforcement path
# only, excluding controller CPU and memory footprint, which is part of the
# overhead CA2 asks about.
#
# Scaling order matters. Kyverno's webhooks carry failurePolicy=Fail, so with
# the pods at zero and the webhooks still registered the API server rejects
# everything. The controllers are therefore scaled down FIRST and the webhooks
# removed AFTER. Kyverno recreates its own webhooks on startup, so this is
# reversible.
#
# Gatekeeper's webhook is a static Helm artefact and is NEVER deleted -- doing
# so destroyed it on 26 July and silently invalidated ten hours of data. It is
# neutralised by patching objectSelector instead, which is reversible.
#
# USAGE
#   ./scripts/benchmark-rcbd.sh [BLOCKS] [REPS] [ARGOCD_APP]
#   ./scripts/benchmark-rcbd.sh 10 5          # 50 cycles per config, as CA2
#   WARMUP=3 ./scripts/benchmark-rcbd.sh 1 2  # pilot, ~6 minutes
#
# Expect roughly 60-90 minutes for the full run. Leave it undisturbed: your own
# browser tabs are exactly the system load that corrupted the first attempt.
# =============================================================================

set -uo pipefail   # -e omitted deliberately: v1 died silently on empty greps

BLOCKS="${1:-10}"
REPS="${2:-5}"
ARGOCD_APP="${3:-dora-bench-compliant}"
WARMUP="${WARMUP:-5}"
LOAD_CEILING="${LOAD_CEILING:-6.0}"
SETTLE="${SETTLE:-15}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RESULTS_DIR="$REPO_DIR/results"
PROBE_BAD="$REPO_DIR/manifests/non-compliant/req010-violation.yaml"
GK_WH="gatekeeper-validating-webhook-configuration"
SENTINEL='{"matchLabels":{"dora-isolation/disabled":"true"}}'
BACKUP="$REPO_DIR/evidence/forensics/all-webhooks-20260726-131348.yaml"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUTFILE="$RESULTS_DIR/benchmark-rcbd-${TIMESTAMP}.csv"
mkdir -p "$RESULTS_DIR"

GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${GREEN}[✓]${NC} $1"; }
info() { echo -e "${BLUE}[i]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; }

# --- guaranteed recovery -------------------------------------------------------
# Twice now an aborted run has left Kyverno's webhooks registered with the pods
# at zero replicas. failurePolicy=Fail with no backend means the API server
# rejects EVERY write in the cluster, including the deletes needed to clean up.
# This trap fires on normal exit, Ctrl-C, and kill, so the cluster can never be
# left in that state again.
RESTORED=0
restore_all() {
    [ "$RESTORED" -eq 1 ] && return
    RESTORED=1
    echo ""
    info "Restoring engines (exit trap)..."
    kubectl scale deployment -n kyverno --all --replicas=1 >/dev/null 2>&1
    kubectl scale deployment -n gatekeeper-system --all --replicas=1 >/dev/null 2>&1
    kubectl wait --for=condition=ready pod --all -n kyverno --timeout=240s >/dev/null 2>&1
    local waited=0
    while [ "$waited" -lt 240 ]; do
        [ "$(kubectl get validatingwebhookconfigurations --no-headers 2>/dev/null \
             | grep -c '^kyverno-')" -ge 7 ] && break
        sleep 5; waited=$((waited+5))
        printf "\r    restoring Kyverno webhooks (%ds)   " "$waited"
    done
    gk_webhook on >/dev/null 2>&1
    echo ""
    local n
    n=$(kubectl get validatingwebhookconfigurations --no-headers 2>/dev/null | wc -l)
    [ "$n" -eq 8 ] && log "Cluster restored: $n webhook configs" \
                   || err "Cluster NOT fully restored: $n/8 webhook configs — run '$0 recover'"
}
trap restore_all EXIT INT TERM

KYVERNO_WH=(
  kyverno-resource-validating-webhook-cfg
  kyverno-policy-validating-webhook-cfg
  kyverno-exception-validating-webhook-cfg
  kyverno-cel-exception-validating-webhook-cfg
  kyverno-global-context-validating-webhook-cfg
  kyverno-cleanup-validating-webhook-cfg
  kyverno-ttl-validating-webhook-cfg
)

# --- engine control -----------------------------------------------------------
kyverno_down() {
    kubectl scale deployment -n kyverno --all --replicas=0 >/dev/null 2>&1
    kubectl wait --for=delete pod --all -n kyverno --timeout=120s >/dev/null 2>&1
    # Only AFTER the pods are gone: failurePolicy=Fail with no backend blocks
    # every write in the cluster.
    kubectl delete validatingwebhookconfiguration "${KYVERNO_WH[@]}" \
        --ignore-not-found >/dev/null 2>&1
}

kyverno_up() {
    kubectl scale deployment -n kyverno --all --replicas=1 >/dev/null 2>&1
    kubectl wait --for=condition=ready pod --all -n kyverno --timeout=180s >/dev/null 2>&1
    # Poll for webhook re-registration rather than guessing a sleep duration.
    # After scaling from zero Kyverno takes 30-60s to rebuild its seven webhook
    # configurations. A fixed 15s sleep let timing start before the engine was
    # in the admission path -- the same class of error as the 26 July run.
    local waited=0
    while [ "$waited" -lt 300 ]; do
        local n
        n=$(kubectl get validatingwebhookconfigurations --no-headers 2>/dev/null \
            | grep -c "^kyverno-")
        [ "$n" -ge 7 ] && { sleep 8; return 0; }
        sleep 5; waited=$((waited + 5))
        printf "\r    waiting for Kyverno webhooks: %d/7 (%ds)   " "$n" "$waited"
    done
    warn "Kyverno webhooks did not reach 7 within 300s"
    return 1
}

gatekeeper_down() {
    kubectl scale deployment -n gatekeeper-system --all --replicas=0 >/dev/null 2>&1
    kubectl wait --for=delete pod --all -n gatekeeper-system --timeout=120s >/dev/null 2>&1
    gk_webhook off
}

gatekeeper_up() {
    kubectl scale deployment -n gatekeeper-system --all --replicas=1 >/dev/null 2>&1
    kubectl wait --for=condition=ready pod -l control-plane=controller-manager \
        -n gatekeeper-system --timeout=180s >/dev/null 2>&1
    gk_webhook on
    sleep 10
}

gk_webhook() {   # on | off — NEVER delete this object
    kubectl get validatingwebhookconfiguration "$GK_WH" >/dev/null 2>&1 || return 1
    local n patch i=0
    n=$(kubectl get validatingwebhookconfiguration "$GK_WH" \
        -o jsonpath='{.webhooks[*].name}' 2>/dev/null | wc -w)
    patch="["
    while [ "$i" -lt "$n" ]; do
        [ "$i" -gt 0 ] && patch="$patch,"
        if [ "$1" = "off" ]; then
            patch="$patch{\"op\":\"replace\",\"path\":\"/webhooks/$i/objectSelector\",\"value\":$SENTINEL}"
        else
            patch="$patch{\"op\":\"replace\",\"path\":\"/webhooks/$i/objectSelector\",\"value\":{}}"
        fi
        i=$((i + 1))
    done
    kubectl patch validatingwebhookconfiguration "$GK_WH" --type=json -p "$patch]" >/dev/null 2>&1
}

apply_config() {
    case "$1" in
        baseline)   kyverno_down; gatekeeper_down ;;
        kyverno)    kyverno_up;   gatekeeper_down ;;
        gatekeeper) kyverno_down; gatekeeper_up   ;;
    esac
    sleep "$SETTLE"
}

# Behavioural gate. Status fields lie: on 26 July both engines reported healthy
# pods and active constraints while Gatekeeper had no webhook at all. Only a real
# admission attempt is trustworthy, so every configuration is verified before any
# timing is recorded.
verify_config() {
    local cfg="$1" out attempt=0
    # Retry with backoff: webhook registration is eventually consistent, so a
    # single probe can fail while the engine is still coming up. Three attempts
    # over ~45s distinguishes "not ready yet" from "not isolated correctly".
    while [ "$attempt" -lt 3 ]; do
        out=$(kubectl apply --dry-run=server -f "$PROBE_BAD" 2>&1)
        case "$cfg" in
            baseline)   echo "$out" | grep -q "dry run"     && return 0 ;;
            kyverno)    echo "$out" | grep -qi "kyverno"    && return 0 ;;
            gatekeeper) echo "$out" | grep -qi "gatekeeper" && return 0 ;;
        esac
        attempt=$((attempt + 1))
        [ "$attempt" -lt 3 ] && { printf "\r    verify retry %d/3 for %s   " "$attempt" "$cfg"; sleep 15; }
    done
    echo ""
    err "verification FAILED for '$cfg' after 3 attempts"; echo "$out" | head -3; return 1
}

# --- measurement --------------------------------------------------------------
# CA2's primary metric. --replace forces genuine resource replacement each cycle,
# so every object traverses the admission path; a plain sync on an unchanged
# application is a no-op and would measure nothing.
measure_argocd_sync_ms() {
    local s e
    s=$(date +%s%N)
    # --replace was removed: it deletes and recreates Deployments, so the timing
    # was dominated by nginx pod termination and rescheduling (197s per cycle)
    # rather than by admission. --force alone pushes every resource through the
    # API server, so each object still traverses the admission webhooks.
    # Waiting on --sync only, never --health, for the same reason.
    argocd app sync "$ARGOCD_APP" --force --timeout 180 >/dev/null 2>&1
    argocd app wait "$ARGOCD_APP" --sync --timeout 180 >/dev/null 2>&1
    e=$(date +%s%N)
    echo $(( (e - s) / 1000000 ))
}

run_cycle() {
    local block="$1" cfg="$2" rep="$3" pos="$4"
    local lb la sync flag
    lb=$(awk '{print $1}' /proc/loadavg)
    sync=$(measure_argocd_sync_ms)
    la=$(awk '{print $1}' /proc/loadavg)

    # Flagged, not dropped. Removing observations post hoc is a researcher degree
    # of freedom an examiner will ask about; flagging lets the analysis run both
    # with and without them.
    flag="ok"
    (( $(echo "$lb > $LOAD_CEILING" | bc -l 2>/dev/null || echo 0) )) && flag="high_load"

    echo "$block,$cfg,$rep,$pos,$sync,$sync,0,$lb,$la,$flag,$(date -Iseconds)" >> "$OUTFILE"
    printf "\r    %-11s rep %d/%d  sync=%6sms  load=%-5s %s      " \
        "$cfg" "$rep" "$REPS" "$sync" "$lb" \
        "$([ "$flag" = high_load ] && echo '[HIGH LOAD]')"
}

# --- pre-flight ---------------------------------------------------------------
# Standalone recovery, for when a previous run left the cluster wedged.
if [ "${1:-}" = "recover" ]; then
    trap - EXIT INT TERM
    info "Recovering cluster state..."
    kubectl scale deployment -n kyverno --all --replicas=1 >/dev/null 2>&1
    kubectl scale deployment -n gatekeeper-system --all --replicas=1 >/dev/null 2>&1
    kubectl wait --for=condition=ready pod --all -n kyverno --timeout=240s >/dev/null 2>&1
    w=0
    while [ "$w" -lt 240 ]; do
        n=$(kubectl get validatingwebhookconfigurations --no-headers 2>/dev/null | grep -c '^kyverno-')
        [ "$n" -ge 7 ] && break
        sleep 5; w=$((w+5)); printf "\r    Kyverno webhooks: %d/7 (%ds)   " "$n" "$w"
    done
    echo ""
    gk_webhook on >/dev/null 2>&1
    kubectl get validatingwebhookconfigurations --no-headers | wc -l
    log "Recovery complete"
    exit 0
fi

# Scaling four Kyverno controllers back up needs headroom. If the node is
# already tight, kyverno_up times out and the run aborts mid-block.
FREE_MB=$(free -m | awk '/^Mem:/{print $7}')
if [ "${FREE_MB:-0}" -lt 1500 ]; then
    err "Only ${FREE_MB}MB available memory. Free at least 1500MB before running."
    err "Try: kubectl delete deployments --all -n dora-test; wsl.exe --shutdown (then reopen)"
    exit 1
fi
info "Available memory: ${FREE_MB}MB"

command -v argocd >/dev/null 2>&1 || { err "argocd CLI not found — required for the CA2 sync metric"; exit 1; }
argocd app get "$ARGOCD_APP" >/dev/null 2>&1 || {
    err "cannot reach ArgoCD app '$ARGOCD_APP'."
    err "Run: kubectl port-forward svc/argocd-server -n argocd 8080:443 & then argocd login"; exit 1; }
[ -f "$PROBE_BAD" ] || { err "missing probe manifest: $PROBE_BAD"; exit 1; }
kubectl get validatingwebhookconfiguration "$GK_WH" >/dev/null 2>&1 || {
    err "Gatekeeper webhook absent. Restore: kubectl apply -f $BACKUP"; exit 1; }

echo "cycle_block,configuration,rep,order_in_block,argocd_sync_ms,admission_ms,webhook_delta_ms,load_before,load_after,quality_flag,timestamp" > "$OUTFILE"

cat <<BANNER

=============================================================
 DORA-as-Code — Phase 4 benchmark (CA2-aligned, RCBD)
=============================================================
 Primary metric:      ArgoCD sync duration (per CA2)
 Blocks:              $BLOCKS
 Reps per block:      $REPS
 Cycles/config:       $((BLOCKS * REPS))   (CA2 specifies 50)
 Baseline:            controllers scaled to 0 (true no-engine)
 ArgoCD app:          $ARGOCD_APP
 Output:              $(basename "$OUTFILE")
=============================================================

BANNER

info "Warm-up: $WARMUP discarded sync cycles"
apply_config baseline
for i in $(seq 1 "$WARMUP"); do
    measure_argocd_sync_ms >/dev/null
    printf "\r    warm-up %d/%d" "$i" "$WARMUP"
done
echo ""; log "Warm-up complete"; echo ""

ABORTED=0
for block in $(seq 1 "$BLOCKS"); do
    ORDER=$(printf "baseline\nkyverno\ngatekeeper\n" | shuf)
    info "Block $block/$BLOCKS — order: $(echo "$ORDER" | tr '\n' ' ')"
    pos=0
    while read -r cfg; do
        [ -z "$cfg" ] && continue
        pos=$((pos + 1))
        apply_config "$cfg"
        if ! verify_config "$cfg"; then
            err "Aborting in block $block: '$cfg' did not isolate correctly."
            err "Partial data in $OUTFILE is INCOMPLETE — do not analyse it."
            ABORTED=1; break 2
        fi
        for rep in $(seq 1 "$REPS"); do run_cycle "$block" "$cfg" "$rep" "$pos"; done
        echo ""
    done <<< "$ORDER"
done

echo ""
# The EXIT trap performs the restore; calling it here would duplicate the work.
info "Run finished — exit trap will restore engines."
echo ""
echo "Webhook configs: $(kubectl get validatingwebhookconfigurations --no-headers 2>/dev/null | wc -l) (expect 8)"
echo "Policy modes:"
kubectl get clusterpolicies -o custom-columns='A:.spec.validationFailureAction' \
    --no-headers 2>/dev/null | sort | uniq -c

[ "$ABORTED" -eq 1 ] && { err "Run aborted — dataset unusable."; exit 1; }

echo ""
log "Benchmark complete: $OUTFILE"
info "Rows: $(( $(wc -l < "$OUTFILE") - 1 ))"
info "Next: python3 scripts/analyse-benchmarks.py --rcbd $OUTFILE --out results/analysis-rcbd"
