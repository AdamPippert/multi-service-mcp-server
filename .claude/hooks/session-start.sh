#!/bin/bash
# SessionStart hook for multi-service-mcp-server
# This script runs when a Claude Code session starts (web or CLI)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Check if this is a resume vs new session
IS_RESUME=false
if [[ "$1" == "--resume" ]]; then
    IS_RESUME=true
fi

# Function to log messages
log() {
    echo "[MCP Setup] $1"
}

# Set up persistent environment variables for the session
setup_env() {
    if [ -n "$CLAUDE_ENV_FILE" ]; then
        # Python environment
        echo "export PYTHONDONTWRITEBYTECODE=1" >> "$CLAUDE_ENV_FILE"
        echo "export PYTHONUNBUFFERED=1" >> "$CLAUDE_ENV_FILE"

        # Flask configuration
        echo "export FLASK_APP=app.py" >> "$CLAUDE_ENV_FILE"
        echo "export FLASK_ENV=development" >> "$CLAUDE_ENV_FILE"

        # MCP Server defaults
        echo "export MCP_SERVER_PORT=5000" >> "$CLAUDE_ENV_FILE"
        echo "export PUPPETEER_HEADLESS=true" >> "$CLAUDE_ENV_FILE"

        # Memory system profile (S=single, C=cluster, E=enterprise)
        echo "export MEMORY_PROFILE=S" >> "$CLAUDE_ENV_FILE"

        # Add project bin to PATH
        echo "export PATH=\"\$PATH:$PROJECT_ROOT/node_modules/.bin\"" >> "$CLAUDE_ENV_FILE"

        log "Environment variables configured"
    fi
}

# Check and install Python dependencies
setup_python() {
    if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
        if ! pip show flask &>/dev/null 2>&1; then
            log "Installing Python dependencies..."
            pip install -q -r "$PROJECT_ROOT/requirements.txt" 2>/dev/null || true
        else
            log "Python dependencies already installed"
        fi
    fi
}

# Check and install Node.js dependencies
setup_node() {
    if [ -f "$PROJECT_ROOT/package.json" ]; then
        if [ ! -d "$PROJECT_ROOT/node_modules" ]; then
            log "Installing Node.js dependencies..."
            cd "$PROJECT_ROOT" && npm install --silent 2>/dev/null || true
        else
            log "Node.js dependencies already installed"
        fi
    fi
}

# Verify the environment is ready
verify_setup() {
    local issues=0

    # Check Python
    if ! command -v python3 &>/dev/null; then
        log "Warning: Python 3 not found"
        ((issues++))
    fi

    # Check Node.js
    if ! command -v node &>/dev/null; then
        log "Warning: Node.js not found"
        ((issues++))
    fi

    if [ $issues -eq 0 ]; then
        log "Environment verification passed"
    fi
}

# Main execution
main() {
    log "Initializing MCP Server environment..."

    # Always set up environment variables
    setup_env

    if [ "$IS_RESUME" = true ]; then
        log "Resuming session - skipping dependency installation"
        verify_setup
    else
        log "New session - checking dependencies"
        setup_python
        setup_node
        verify_setup
    fi

    # Print helpful context for Claude
    echo ""
    echo "=== Multi-Service MCP Server ==="
    echo "Available tools: GitHub, GitLab, Google Maps, Memory, Puppeteer"
    echo "Start server: python app.py (runs on port 5000)"
    echo "Test endpoint: curl http://localhost:5000/health"
    echo "MCP Gateway: POST http://localhost:5000/mcp/gateway"
    echo ""

    log "Session initialization complete"
}

main "$@"
exit 0
