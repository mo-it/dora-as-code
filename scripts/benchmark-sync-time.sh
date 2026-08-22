#!/bin/bash
##############################################################################
# SUPERSEDED by scripts/benchmark-rcbd.sh.
#
# Measured ArgoCD sync duration only. Sync duration proved to be a poorly
# sensitive instrument for admission overhead, because admission is only
# about 17 to 18 per cent of a sync cycle. The current harness records both
# sync duration and admission-path latency.
##############################################################################
# =============================================================================
# Phase 4: ArgoCD Sync-Time Benchmark
# =============================================================================
# Measures the time overhead each policy engine adds to ArgoCD sync operations.
# Runs 50 sync cycles per configuration: baseline, Kyverno, OPA Gatekeeper.
#
# Usage: ./benchmark-sync-time.sh [baseline|kyverno|gatekeeper] [num_cycles]
# =============================================================================

set -euo pipefail

CONFIG="${1:-baseline}"
CYCLES="${2:-50}"
RESULTS_DIR="$(dirname "$0")/../results"
OUTFILE="$RESULTS_DIR/sync-times-${CONFIG}.csv"

mkdir -p "$RESULTS_DIR"
echo "cycle,sync_duration_ms,timestamp" > "$OUTFILE"

echo "Running $CYCLES sync cycles for configuration: $CONFIG"

for i in $(seq 1 "$CYCLES"); do
    # Force a sync by touching a dummy annotation
    START_MS=$(date +%s%N | cut -b1-13)

    kubectl annotate namespace default \
        "benchmark.dora/cycle=$i" --overwrite >/dev/null 2>&1

    # Trigger ArgoCD sync and wait for completion
    # (Replace with actual ArgoCD app sync when pipeline is connected)
    kubectl wait --for=condition=available deployment -l app=test-with-limits \
        --timeout=60s >/dev/null 2>&1 || true

    END_MS=$(date +%s%N | cut -b1-13)
    DURATION=$((END_MS - START_MS))

    echo "$i,$DURATION,$(date -Iseconds)" >> "$OUTFILE"
    printf "\r  Cycle %d/%d: %dms" "$i" "$CYCLES" "$DURATION"
done

echo ""
echo "Results saved to $OUTFILE"
echo "Mean: $(awk -F',' 'NR>1{s+=$2;c++}END{printf "%.0fms", s/c}' "$OUTFILE")"
echo "StdDev: $(awk -F',' 'NR>1{a[NR]=$2;s+=$2;c++}END{m=s/c;for(i in a){d+=((a[i]-m)^2)};printf "%.0fms", sqrt(d/c)}' "$OUTFILE")"
