#!/bin/bash
##############################################################################
# SUPERSEDED by scripts/benchmark-rcbd.sh.
#
# This is the fixed sequential harness. It produces valid measurements but
# a sequential design confounds run order with configuration, which is why
# the randomised complete block design replaced it. Kept for reference.
##############################################################################
# =============================================================================
# DORA-as-Code: Phase 4 Benchmark (Fixed)
# =============================================================================
# Usage:
#   ./benchmark-run.sh 5          # Quick test (5 cycles each)
#   ./benchmark-run.sh 50         # Full experiment (50 cycles each)
#   ./benchmark-run.sh 50 kyverno # Single engine only
# =============================================================================

CYCLES="${1:-50}"
ENGINE="${2:-all}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/../results"
MANIFEST_DIR="$SCRIPT_DIR/../manifests"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

mkdir -p "$RESULTS_DIR"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'
log()  { echo -e "${GREEN}[✓]${NC} $1"; }
info() { echo -e "${BLUE}[i]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }

# Create test namespace
kubectl create namespace dora-test 2>/dev/null || true

# Create a ServiceAccount for the test namespace
kubectl create serviceaccount dora-test-sa -n dora-test 2>/dev/null || true

# Get metrics token
TOKEN=$(kubectl create token metrics-reader --duration=120m 2>/dev/null || echo "")

get_webhook_metric() {
    local pattern="$1"
    if [ -z "$TOKEN" ]; then
        echo "0"
        return
    fi
    local val
    val=$(curl -sk -H "Authorization: Bearer $TOKEN" \
        "https://127.0.0.1:6443/metrics" 2>/dev/null \
        | grep "apiserver_admission_webhook_admission_duration_seconds_sum" \
        | grep -i "$pattern" \
        | awk '{sum+=$NF} END {print sum+0}' 2>/dev/null) || true
    echo "${val:-0}"
}

disable_kyverno() {
    info "Disabling Kyverno..."
    kubectl delete validatingwebhookconfigurations -l app.kubernetes.io/instance=kyverno 2>/dev/null || true
    kubectl delete mutatingwebhookconfigurations -l app.kubernetes.io/instance=kyverno 2>/dev/null || true
    kubectl scale deployment -n kyverno --all --replicas=0 2>/dev/null || true
    sleep 10
    log "Kyverno disabled"
}

disable_gatekeeper() {
    info "Disabling Gatekeeper..."
    kubectl delete validatingwebhookconfigurations gatekeeper-validating-webhook-configuration 2>/dev/null || true
    kubectl delete mutatingwebhookconfigurations gatekeeper-mutating-webhook-configuration 2>/dev/null || true
    kubectl scale deployment -n gatekeeper-system --all --replicas=0 2>/dev/null || true
    sleep 10
    log "Gatekeeper disabled"
}

enable_kyverno() {
    info "Enabling Kyverno..."
    kubectl scale deployment -n kyverno --all --replicas=1 2>/dev/null || true
    kubectl wait --for=condition=ready pod -l app.kubernetes.io/component=admission-controller -n kyverno --timeout=120s 2>/dev/null || true
    sleep 15
    log "Kyverno enabled"
}

enable_gatekeeper() {
    info "Enabling Gatekeeper..."
    kubectl scale deployment -n gatekeeper-system --all --replicas=1 2>/dev/null || true
    kubectl wait --for=condition=ready pod -l control-plane=controller-manager -n gatekeeper-system --timeout=120s 2>/dev/null || true
    sleep 15
    log "Gatekeeper enabled"
}

restore_all() {
    info "Restoring both engines..."
    enable_kyverno
    enable_gatekeeper
    log "Both engines restored"
}

run_benchmark() {
    local config_name="$1"
    local webhook_pattern="$2"
    local outfile="$RESULTS_DIR/benchmark-${config_name}-${TIMESTAMP}.csv"

    echo "cycle,sync_duration_ms,webhook_sum_before,webhook_sum_after,load_avg,timestamp" > "$outfile"

    info "Running $CYCLES sync cycles for: $config_name"
    echo ""

    # Use a simple deployment manifest for timing
    local test_manifest="$MANIFEST_DIR/compliant/req006-with-resource-limits.yaml"

    # Clean up any previous test resources
    kubectl delete deployment test-req006-compliant -n dora-test 2>/dev/null || true
    sleep 2

    for i in $(seq 1 "$CYCLES"); do
        load_avg=$(awk '{print $1}' /proc/loadavg)

        # Get webhook metric before
        wb=$(get_webhook_metric "$webhook_pattern")

        # Time the kubectl apply
        start_ms=$(date +%s%3N)

        kubectl apply -f "$test_manifest" -n dora-test 2>/dev/null || true
        sleep 0.5

        # Delete and recreate to force a fresh admission on each cycle
        kubectl delete deployment test-req006-compliant -n dora-test 2>/dev/null || true
        sleep 0.5

        end_ms=$(date +%s%3N)
        duration=$((end_ms - start_ms))

        # Get webhook metric after
        wa=$(get_webhook_metric "$webhook_pattern")

        echo "$i,$duration,$wb,$wa,$load_avg,$(date -Iseconds)" >> "$outfile"
        printf "\r  Cycle %d/%d: %dms (load: %s)" "$i" "$CYCLES" "$duration" "$load_avg"
    done

    echo ""
    echo ""

    # Summary
    log "Results saved to $outfile"
    echo "  Summary for $config_name:"
    awk -F',' 'NR>1 {
        s+=$2; c++
        if(NR==2 || $2>mx) mx=$2
        if(NR==2 || $2<mn) mn=$2
        a[NR]=$2
    } END {
        mean=s/c
        for(i in a) {d+=(a[i]-mean)^2}
        sd=sqrt(d/c)
        printf "    Mean:   %.0f ms\n", mean
        printf "    StdDev: %.0f ms\n", sd
        printf "    Min:    %d ms\n", mn
        printf "    Max:    %d ms\n", mx
        printf "    Cycles: %d\n", c
    }' "$outfile"
    echo ""
}

# =============================================================================
# MAIN
# =============================================================================

echo ""
echo "============================================="
echo "  DORA-as-Code Benchmark"
echo "  Cycles: $CYCLES | Config: $ENGINE"
echo "  Started: $(date)"
echo "============================================="
echo ""

# Warn about warm-up
warn "First 5 cycles of each run may have higher variance (cold cache). Consider discarding in analysis."
echo ""

if [ "$ENGINE" = "all" ] || [ "$ENGINE" = "baseline" ]; then
    echo "================================================"
    echo "  Phase 1/3: BASELINE (no policy engine)"
    echo "================================================"
    disable_kyverno
    disable_gatekeeper
    sleep 10
    run_benchmark "baseline" "NOMATCH_BASELINE"
fi

if [ "$ENGINE" = "all" ] || [ "$ENGINE" = "kyverno" ]; then
    echo "================================================"
    echo "  Phase 2/3: KYVERNO ONLY"
    echo "================================================"
    disable_gatekeeper
    enable_kyverno
    sleep 10
    run_benchmark "kyverno" "kyverno"
fi

if [ "$ENGINE" = "all" ] || [ "$ENGINE" = "gatekeeper" ]; then
    echo "================================================"
    echo "  Phase 3/3: GATEKEEPER ONLY"
    echo "================================================"
    disable_kyverno
    enable_gatekeeper
    sleep 10
    run_benchmark "gatekeeper" "gatekeeper"
fi

# Restore
restore_all

echo ""
echo "============================================="
echo "  ✓ BENCHMARK COMPLETE"
echo "============================================="
echo ""
echo "Result files:"
ls -la "$RESULTS_DIR"/benchmark-*-"$TIMESTAMP".csv 2>/dev/null
echo ""
echo "Verify engines restored:"
kubectl get clusterpolicy --no-headers 2>/dev/null | wc -l
kubectl get constraints --no-headers 2>/dev/null | wc -l
echo ""
echo "To analyse: import CSV into Excel/Python/R"
echo "Columns: cycle, sync_duration_ms, webhook_sum_before, webhook_sum_after, load_avg, timestamp"
echo ""
