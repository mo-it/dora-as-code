#!/bin/bash
##############################################################################
# SUPERSEDED. Do not use.
#
# This harness exited silently under `set -euo pipefail` whenever `grep`
# returned exit code 1 on empty metrics output, so runs appeared to finish
# when they had aborted partway. Replaced by benchmark-run.sh (which adds
# || true on every grep/curl/kubectl) and then by benchmark-rcbd.sh, which
# is the current harness. Retained because the failure is cited in the
# dissertation.
##############################################################################
# =============================================================================
# DORA-as-Code: Full Comparative Benchmark Harness
# =============================================================================
#
# Runs the complete Phase 4 benchmark sequence:
#   1. Baseline (no policy engine)      → 50 sync cycles
#   2. Kyverno only                     → 50 sync cycles
#   3. Gatekeeper only                  → 50 sync cycles
#
# For each cycle, records:
#   - ArgoCD sync duration (end-to-end)
#   - Webhook admission duration (per-request, from API server metrics)
#   - System load average (to detect confounding variables)
#   - Timestamp
#
# Usage:
#   ./benchmark-full.sh              # Run all 3 configs, 50 cycles each
#   ./benchmark-full.sh 10           # Run all 3 configs, 10 cycles each (quick test)
#   ./benchmark-full.sh 50 kyverno   # Run only Kyverno, 50 cycles
#
# Prerequisites:
#   - K3s running with ArgoCD, Kyverno, Gatekeeper installed
#   - Test manifests in ../manifests/
#   - metrics-reader ServiceAccount created (run dora-optimizations.sh first)
#
# Output: CSV files in ../results/ ready for analysis
# =============================================================================

set -euo pipefail

CYCLES="${1:-50}"
ENGINE="${2:-all}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/../results"
ISOLATE_SCRIPT="$SCRIPT_DIR/isolate-engine.sh"
MANIFEST_DIR="$SCRIPT_DIR/../manifests"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

mkdir -p "$RESULTS_DIR"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'
log()  { echo -e "${GREEN}[✓]${NC} $1"; }
info() { echo -e "${BLUE}[i]${NC} $1"; }

# Create the test namespace if it doesn't exist
kubectl create namespace dora-test 2>/dev/null || true

# Get API server metrics token
TOKEN=$(kubectl create token metrics-reader --duration=60m 2>/dev/null)
API_SERVER="https://127.0.0.1:6443"

get_webhook_metrics() {
    # Returns the total webhook duration for a specific engine
    local engine_pattern="$1"
    curl -sk -H "Authorization: Bearer $TOKEN" "$API_SERVER/metrics" 2>/dev/null | \
        grep "apiserver_admission_webhook_admission_duration_seconds_sum" | \
        grep -i "$engine_pattern" | \
        awk '{sum+=$NF} END {printf "%.6f", sum+0}'
}

run_benchmark() {
    local config_name="$1"
    local outfile="$RESULTS_DIR/benchmark-${config_name}-${TIMESTAMP}.csv"
    local webhook_pattern="$2"

    echo "cycle,sync_duration_ms,webhook_duration_delta_ms,load_avg_1m,timestamp" > "$outfile"

    info "Running $CYCLES sync cycles for: $config_name"

    for i in $(seq 1 "$CYCLES"); do
        # Record system load (to check for confounding variables)
        load_avg=$(awk '{print $1}' /proc/loadavg)

        # Record webhook metric BEFORE the sync
        webhook_before=$(get_webhook_metrics "$webhook_pattern")

        # Trigger a sync by applying a test manifest with a unique annotation
        START_NS=$(date +%s%N)

        # Apply a known-compliant manifest to measure overhead
        kubectl apply -f "$MANIFEST_DIR/compliant/req006-with-resource-limits.yaml" \
            -n dora-test --overwrite 2>/dev/null || true

        # Small delay to ensure admission is processed
        sleep 0.5

        END_NS=$(date +%s%N)
        DURATION_MS=$(( (END_NS - START_NS) / 1000000 ))

        # Record webhook metric AFTER the sync
        webhook_after=$(get_webhook_metrics "$webhook_pattern")

        # Calculate the delta (time spent in webhook during THIS cycle)
        webhook_delta_ms=$(echo "scale=3; ($webhook_after - $webhook_before) * 1000" | bc 2>/dev/null || echo "0")

        echo "$i,$DURATION_MS,$webhook_delta_ms,$load_avg,$(date -Iseconds)" >> "$outfile"
        printf "\r  Cycle %d/%d: sync=%dms webhook=%.1fms load=%s" \
            "$i" "$CYCLES" "$DURATION_MS" "$webhook_delta_ms" "$load_avg"
    done

    echo ""
    log "Results saved to $outfile"

    # Print summary statistics
    echo "  Summary:"
    awk -F',' 'NR>1 {
        s+=$2; w+=$3; c++
        if($2>max_s) max_s=$2; if(c==1||$2<min_s) min_s=$2
    } END {
        printf "    Sync time:    mean=%.0fms  min=%dms  max=%dms  (n=%d)\n", s/c, min_s, max_s, c
        printf "    Webhook time: mean=%.1fms  total=%.1fms\n", w/c, w
    }' "$outfile"
    echo ""
}

# Clean up any previous test resources
kubectl delete -f "$MANIFEST_DIR/compliant/" -n dora-test 2>/dev/null || true

echo ""
echo "============================================="
echo "  DORA-as-Code Benchmark Suite"
echo "  Cycles: $CYCLES | Config: $ENGINE"
echo "  Started: $(date)"
echo "============================================="
echo ""

if [ "$ENGINE" = "all" ] || [ "$ENGINE" = "baseline" ]; then
    info "--- Phase 1/3: BASELINE (no policy engine) ---"
    "$ISOLATE_SCRIPT" baseline
    sleep 15  # Let the system settle after engine changes
    run_benchmark "baseline" "NOMATCH"
fi

if [ "$ENGINE" = "all" ] || [ "$ENGINE" = "kyverno" ]; then
    info "--- Phase 2/3: KYVERNO ONLY ---"
    "$ISOLATE_SCRIPT" kyverno
    sleep 15
    run_benchmark "kyverno" "kyverno"
fi

if [ "$ENGINE" = "all" ] || [ "$ENGINE" = "gatekeeper" ]; then
    info "--- Phase 3/3: GATEKEEPER ONLY ---"
    "$ISOLATE_SCRIPT" gatekeeper
    sleep 15
    run_benchmark "gatekeeper" "gatekeeper"
fi

# Restore both engines
info "Restoring both engines..."
"$ISOLATE_SCRIPT" restore

echo ""
echo "============================================="
echo "  ✓ BENCHMARK COMPLETE"
echo "============================================="
echo ""
echo "Results in: $RESULTS_DIR/"
ls -la "$RESULTS_DIR"/benchmark-*-"$TIMESTAMP".csv 2>/dev/null
echo ""
echo "Next: analyse results with your preferred tool (Python/R/Excel)"
echo "  CSV columns: cycle, sync_duration_ms, webhook_duration_delta_ms, load_avg_1m, timestamp"
echo ""
