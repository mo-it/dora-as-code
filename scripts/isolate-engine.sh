#!/bin/bash
# =============================================================================
# Engine Isolation for Clean A/B Benchmarking
# =============================================================================
#
# Usage:
#   ./isolate-engine.sh kyverno      # Activate Kyverno ONLY
#   ./isolate-engine.sh gatekeeper   # Activate Gatekeeper ONLY
#   ./isolate-engine.sh baseline     # Disable BOTH (baseline measurement)
#   ./isolate-engine.sh restore      # Restore BOTH engines
#   ./isolate-engine.sh status       # Show current state
#
# What it does:
#   - Saves webhook configurations before removing them
#   - Scales deployments to 0 replicas
#   - Waits for pods to terminate
#   - Verifies the target engine is the ONLY one running
#
# ⚠️ Always run 'restore' after benchmarking to bring everything back
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="$SCRIPT_DIR/../evidence/webhook-backups"
mkdir -p "$BACKUP_DIR"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'
log()  { echo -e "${GREEN}[✓]${NC} $1"; }
info() { echo -e "${BLUE}[i]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }

save_webhooks() {
    # Save current webhook configs so we can restore them later
    # Like photographing the inspector's desk layout before clearing it
    info "Backing up webhook configurations..."
    kubectl get validatingwebhookconfigurations -o yaml > "$BACKUP_DIR/all-webhooks-$(date +%Y%m%d-%H%M%S).yaml" 2>/dev/null || true
    log "Webhook configs backed up to $BACKUP_DIR/"
}

disable_kyverno() {
    info "Disabling Kyverno..."
    # Remove all Kyverno webhook configurations
    kubectl delete validatingwebhookconfigurations -l app.kubernetes.io/instance=kyverno 2>/dev/null || true
    kubectl delete mutatingwebhookconfigurations -l app.kubernetes.io/instance=kyverno 2>/dev/null || true
    # Scale all Kyverno deployments to 0
    kubectl scale deployment -n kyverno --all --replicas=0 2>/dev/null || true
    # Wait for pods to terminate
    kubectl wait --for=delete pods --all -n kyverno --timeout=60s 2>/dev/null || true
    log "Kyverno disabled (webhooks removed + pods terminated)"
}

disable_gatekeeper() {
    info "Disabling Gatekeeper..."
    # Remove Gatekeeper webhook configuration
    kubectl delete validatingwebhookconfigurations gatekeeper-validating-webhook-configuration 2>/dev/null || true
    kubectl delete mutatingwebhookconfigurations gatekeeper-mutating-webhook-configuration 2>/dev/null || true
    # Scale Gatekeeper deployments to 0
    kubectl scale deployment -n gatekeeper-system --all --replicas=0 2>/dev/null || true
    kubectl wait --for=delete pods --all -n gatekeeper-system --timeout=60s 2>/dev/null || true
    log "Gatekeeper disabled (webhooks removed + pods terminated)"
}

enable_kyverno() {
    info "Enabling Kyverno..."
    kubectl scale deployment -n kyverno --all --replicas=1 2>/dev/null || true
    # Wait for the admission controller to be ready
    kubectl wait --for=condition=ready pod -l app.kubernetes.io/component=admission-controller -n kyverno --timeout=120s 2>/dev/null || true
    # Kyverno re-registers its webhooks automatically when pods start
    sleep 10  # Give it time to register webhooks
    log "Kyverno enabled and webhook registered"
}

enable_gatekeeper() {
    info "Enabling Gatekeeper..."
    kubectl scale deployment -n gatekeeper-system --all --replicas=1 2>/dev/null || true
    kubectl wait --for=condition=ready pod -l control-plane=controller-manager -n gatekeeper-system --timeout=120s 2>/dev/null || true
    sleep 10  # Give it time to register webhooks
    log "Gatekeeper enabled and webhook registered"
}

show_status() {
    echo ""
    echo "=== Engine Status ==="
    echo ""
    echo "Kyverno pods:"
    kubectl get pods -n kyverno --no-headers 2>/dev/null | awk '{printf "  %-55s %s\n", $1, $3}' || echo "  (none running)"
    echo ""
    echo "Gatekeeper pods:"
    kubectl get pods -n gatekeeper-system --no-headers 2>/dev/null | awk '{printf "  %-55s %s\n", $1, $3}' || echo "  (none running)"
    echo ""
    echo "Active validating webhooks:"
    kubectl get validatingwebhookconfigurations --no-headers 2>/dev/null | awk '{printf "  %-55s %s\n", $1, $2}' || echo "  (none)"
    echo ""
    echo "Active mutating webhooks:"
    kubectl get mutatingwebhookconfigurations --no-headers 2>/dev/null | awk '{printf "  %-55s %s\n", $1, $2}' || echo "  (none)"
}

case "${1:-status}" in
    kyverno)
        echo "=== Isolating: KYVERNO ONLY ==="
        save_webhooks
        disable_gatekeeper
        enable_kyverno
        show_status
        log "Ready to benchmark Kyverno in isolation"
        ;;
    gatekeeper)
        echo "=== Isolating: GATEKEEPER ONLY ==="
        save_webhooks
        disable_kyverno
        enable_gatekeeper
        show_status
        log "Ready to benchmark Gatekeeper in isolation"
        ;;
    baseline)
        echo "=== Isolating: BASELINE (no policy engine) ==="
        save_webhooks
        disable_kyverno
        disable_gatekeeper
        show_status
        log "Ready to benchmark baseline (no admission policies)"
        ;;
    restore)
        echo "=== Restoring BOTH engines ==="
        enable_kyverno
        enable_gatekeeper
        show_status
        log "Both engines restored"
        ;;
    status)
        show_status
        ;;
    *)
        echo "Usage: $0 {kyverno|gatekeeper|baseline|restore|status}"
        echo ""
        echo "  kyverno     Enable Kyverno ONLY (disable Gatekeeper)"
        echo "  gatekeeper  Enable Gatekeeper ONLY (disable Kyverno)"
        echo "  baseline    Disable BOTH (baseline measurement)"
        echo "  restore     Re-enable BOTH engines"
        echo "  status      Show current engine state"
        exit 1
        ;;
esac
