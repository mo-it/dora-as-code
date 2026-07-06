#!/bin/bash
# =============================================================================
# Collect admission webhook duration metrics from the K3s API server
# =============================================================================
# Usage:
#   ./collect-webhook-metrics.sh                    # Show current metrics
#   ./collect-webhook-metrics.sh --save kyverno     # Save snapshot to CSV
#   ./collect-webhook-metrics.sh --compare          # Compare Kyverno vs Gatekeeper
#
# What this measures:
#   apiserver_admission_webhook_admission_duration_seconds
#   — The exact time the API server waited for each webhook to respond
#   — Broken down by webhook name, operation type, and result
#
# ⚠️ ALPHA metric: document this status in your dissertation
# =============================================================================

set -euo pipefail

RESULTS_DIR="$(dirname "$0")/../results"
mkdir -p "$RESULTS_DIR"

# Get a token for the metrics-reader service account
# Think of this like getting a staff badge to access the kitchen's timer logs
TOKEN=$(kubectl create token metrics-reader --duration=10m 2>/dev/null)
API_SERVER="https://127.0.0.1:6443"

fetch_metrics() {
    curl -sk \
        -H "Authorization: Bearer $TOKEN" \
        "$API_SERVER/metrics" 2>/dev/null | \
        grep "apiserver_admission_webhook_admission_duration_seconds"
}

case "${1:-}" in
    --save)
        ENGINE="${2:-snapshot}"
        OUTFILE="$RESULTS_DIR/webhook-metrics-${ENGINE}-$(date +%Y%m%d-%H%M%S).txt"
        fetch_metrics > "$OUTFILE"
        echo "Saved to $OUTFILE"
        echo "Lines: $(wc -l < "$OUTFILE")"
        ;;
    --compare)
        echo "=== Kyverno webhook durations ==="
        fetch_metrics | grep -i "kyverno" | grep "_sum\|_count" | head -10
        echo ""
        echo "=== Gatekeeper webhook durations ==="
        fetch_metrics | grep -i "gatekeeper" | grep "_sum\|_count" | head -10
        echo ""
        echo "=== Summary ==="
        # Calculate average duration per webhook
        fetch_metrics | grep "_sum{" | while IFS= read -r line; do
            name=$(echo "$line" | grep -oP 'name="[^"]*"' | head -1)
            sum=$(echo "$line" | awk '{print $NF}')
            # Find matching count
            count_line=$(fetch_metrics | grep "_count{" | grep "$name" | head -1)
            count=$(echo "$count_line" | awk '{print $NF}')
            if [ -n "$count" ] && [ "$count" != "0" ]; then
                avg=$(echo "scale=4; $sum / $count * 1000" | bc 2>/dev/null || echo "N/A")
                echo "  $name avg=${avg}ms (${count} calls)"
            fi
        done
        ;;
    *)
        echo "Current admission webhook metrics:"
        echo ""
        fetch_metrics | grep -E "_(sum|count)\{" | sort
        echo ""
        echo "Usage:"
        echo "  $0 --save [engine]    Save metrics snapshot"
        echo "  $0 --compare          Compare Kyverno vs Gatekeeper"
        ;;
esac
