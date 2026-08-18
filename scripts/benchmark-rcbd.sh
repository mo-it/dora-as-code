#!/bin/bash
# =============================================================================
# benchmark-rcbd.sh — Phase 4 benchmark, randomised complete block design
# =============================================================================
#
# WHY THIS REPLACES benchmark-full.sh
# -----------------------------------
# The original harness ran all 50 baseline cycles, then all 50 Kyverno cycles,
# then all 50 Gatekeeper cycles. That design confounds "which policy engine"
# with "when in the session the measurement happened". Analysis of the
# 20260726-232252 run showed:
#
#   * a strong monotonic downward trend within the Kyverno run
#     (Spearman rho = -0.85, p ~ 1e-14) — the machine got faster as it warmed;
#   * mean system load of 3.14 during baseline vs 1.42 during Kyverno;
#   * a significant positive load/duration correlation (rho = 0.26, p = 0.001).
#
# Net effect: the baseline appeared SLOWER than running with an admission
# webhook, which is physically implausible. The difference was session drift,
# not engine behaviour.
#
# A randomised complete block design fixes this. Time is divided into blocks.
# Every configuration is measured once inside every block, in a randomised
# order. Any slow drift affects all three configurations roughly equally,
# so it cancels in the between-configuration comparison instead of loading
# onto whichever config happened to run first.
#
# Café analogy: the old design timed the espresso bar all morning, the pastry
# counter all afternoon, and the kitchen all evening — then blamed the pastry
# counter for being slow, when really the whole café just gets busier as the
# day goes on. The new design times all three counters once an hour, every
# hour. Rush hour hits all of them, so the comparison stays fair.
#
# WHAT IT MEASURES
# ----------------
# Two distinct metrics, reported separately (the original conflated them):
#
#   1. admission_ms  — kubectl apply round-trip through the admission path.
#                      This is the direct policy-engine cost.
#   2. argocd_sync_ms — ArgoCD Application reconciliation to Synced/Healthy.
#                      This is the GitOps pipeline cost the CA2 proposal
#                      actually named.
#
# USAGE
#   ./benchmark-rcbd.sh [BLOCKS] [REPS_PER_BLOCK] [ARGOCD_APP]
#   ./benchmark-rcbd.sh 10 5 dora-test-workloads
#
#   Default 10 blocks x 5 reps = 50 observations per configuration,
#   matching the CA2-proposed sample size with a sound design.
#
# PREREQUISITES
#   kubectl, argocd CLI logged in, bc, python3
#   Run ./isolate-engine.sh restore afterwards.
# =============================================================================

set -uo pipefail   # NOTE: -e deliberately omitted. The original script died
                   # silently when grep found no metrics on baseline runs.

BLOCKS="${1:-10}"
REPS="${2:-5}"
ARGOCD_APP="${3:-dora-bench-compliant}"
WARMUP="${WARMUP:-10}"          # discarded cycles before measurement starts
LOAD_CEILING="${LOAD_CEILING:-6.0}"   # flag cycles taken under extreme load

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/../results"
MANIFEST_DIR="$SCRIPT_DIR/../manifests"
ISOLATE="$SCRIPT_DIR/isolate-engine.sh"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUTFILE="$RESULTS_DIR/benchmark-rcbd-${TIMESTAMP}.csv"

mkdir -p "$RESULTS_DIR"

GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[✓]${NC} $1"; }
info() { echo -e "${BLUE}[i]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }

kubectl create namespace dora-test >/dev/null 2>&1 || true

# --- API server metrics access -----------------------------------------------
TOKEN=$(kubectl create token metrics-reader --duration=180m 2>/dev/null) || true
API_SERVER="https://127.0.0.1:6443"

# The original script grepped for the engine name and got nothing for
# Gatekeeper — 0 of 50 cycles recorded a webhook delta, so the Gatekeeper
# admission timings were never actually captured. These are the real webhook
# names as they appear in the apiserver metric labels.
webhook_pattern_for() {
    case "$1" in
        kyverno)    echo "kyverno" ;;
        gatekeeper) echo "gatekeeper.sh" ;;   # validation.gatekeeper.sh
        *)          echo "__none__" ;;
    esac
}

get_webhook_sum() {
    local pattern="$1"
    [ "$pattern" = "__none__" ] && { echo "0"; return; }
    curl -sk -H "Authorization: Bearer $TOKEN" "$API_SERVER/metrics" 2>/dev/null \
        | grep "apiserver_admission_webhook_admission_duration_seconds_sum" 2>/dev/null \
        | grep -i "$pattern" 2>/dev/null \
        | awk '{sum+=$NF} END {printf "%.6f", sum+0}' || echo "0"
}

# --- measurement primitives ---------------------------------------------------
measure_admission_ms() {
    # kubectl apply round-trip. No sleep inside the timed window — the original
    # baked a fixed 0.5s sleep into the measurement, inflating every reading
    # by a constant and compressing the relative difference between configs.
    local start_ns end_ns
    start_ns=$(date +%s%N)
    kubectl apply -f "$MANIFEST_DIR/compliant/req006-with-resource-limits.yaml" \
        -n dora-test >/dev/null 2>&1 || true
    end_ns=$(date +%s%N)
    echo $(( (end_ns - start_ns) / 1000000 ))
}

measure_argocd_sync_ms() {
    # Real ArgoCD reconciliation: force a sync and wait for Synced + Healthy.
    # Returns -1 if the argocd CLI is unavailable, so the admission metric
    # still gets collected rather than aborting the whole run.
    command -v argocd >/dev/null 2>&1 || { echo "-1"; return; }
    local start_ns end_ns
    start_ns=$(date +%s%N)
    argocd app sync "$ARGOCD_APP" --prune --timeout 120 >/dev/null 2>&1 || true
    argocd app wait "$ARGOCD_APP" --health --sync --timeout 120 >/dev/null 2>&1 || true
    end_ns=$(date +%s%N)
    echo $(( (end_ns - start_ns) / 1000000 ))
}

run_cycle() {
    local block="$1" config="$2" rep="$3" order_pos="$4"
    local pattern load_before load_after wb wa delta_ms adm sync flag

    pattern=$(webhook_pattern_for "$config")
    load_before=$(awk '{print $1}' /proc/loadavg)
    wb=$(get_webhook_sum "$pattern")

    adm=$(measure_admission_ms)
    sync=$(measure_argocd_sync_ms)

    wa=$(get_webhook_sum "$pattern")
    load_after=$(awk '{print $1}' /proc/loadavg)
    delta_ms=$(echo "scale=3; ($wa - $wb) * 1000" | bc 2>/dev/null || echo "0")

    # Flag rather than silently drop. Dropping observations post hoc is a
    # researcher degree of freedom an examiner will ask about; flagging lets
    # the analysis script run the comparison with and without them.
    flag="ok"
    if (( $(echo "$load_before > $LOAD_CEILING" | bc -l 2>/dev/null || echo 0) )); then
        flag="high_load"
    fi

    echo "$block,$config,$rep,$order_pos,$adm,$sync,$delta_ms,$load_before,$load_after,$flag,$(date -Iseconds)" \
        >> "$OUTFILE"

    printf "\r  block %02d | %-11s | rep %d | admission=%5sms sync=%6sms load=%s %s   " \
        "$block" "$config" "$rep" "$adm" "$sync" "$load_before" \
        "$([ "$flag" = "high_load" ] && echo '[HIGH LOAD]' || echo '')"
}

# --- main ---------------------------------------------------------------------
echo "cycle_block,configuration,rep,order_in_block,admission_ms,argocd_sync_ms,webhook_delta_ms,load_before,load_after,quality_flag,timestamp" > "$OUTFILE"

cat <<BANNER

=============================================================
 DORA-as-Code — Phase 4 benchmark (randomised block design)
=============================================================
 Blocks:            $BLOCKS
 Reps per block:    $REPS
 Observations/config: $((BLOCKS * REPS))
 Warm-up discarded: $WARMUP cycles
 ArgoCD app:        $ARGOCD_APP
 Output:            $OUTFILE
=============================================================

BANNER

info "Warm-up: $WARMUP discarded cycles to settle page cache and K3s state"
bash "$ISOLATE" baseline >/dev/null 2>&1 || true
for i in $(seq 1 "$WARMUP"); do
    measure_admission_ms >/dev/null
    printf "\r  warm-up %d/%d" "$i" "$WARMUP"
done
echo ""
log "Warm-up complete"
echo ""

for block in $(seq 1 "$BLOCKS"); do
    # Randomise configuration order independently within each block.
    ORDER=$(printf "baseline\nkyverno\ngatekeeper\n" | shuf)
    info "Block $block/$BLOCKS — order: $(echo "$ORDER" | tr '\n' ' ')"

    pos=0
    while read -r config; do
        [ -z "$config" ] && continue
        pos=$((pos + 1))

        bash "$ISOLATE" "$config" >/dev/null 2>&1 || true
        sleep 15   # let webhook registration settle before timing anything

        for rep in $(seq 1 "$REPS"); do
            run_cycle "$block" "$config" "$rep" "$pos"
        done
        echo ""
    done <<< "$ORDER"
done

echo ""
log "Benchmark complete: $OUTFILE"
info "Restoring both engines..."
bash "$ISOLATE" restore >/dev/null 2>&1 || true
log "Engines restored"

echo ""
info "Next: python3 scripts/analyse-benchmarks.py --rcbd $OUTFILE"
