#!/usr/bin/env bash
# =============================================================================
# start.sh — Edge-Auto-Assistant Launcher
#
# 1. Kills any stale llama-server process
# 2. Starts llama-server (Llama-3.2-1B) on 127.0.0.1:8080 in background
# 3. Waits until server is ready (polls /health endpoint)
# 4. Activates the Python venv
# 5. Launches main.py
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LLAMA_SERVER="${HOME}/llama.cpp/build/bin/llama-server"
MODEL="${HOME}/models/Llama-3.2-1B-Instruct-Q4_K_M.gguf"
VENV="${SCRIPT_DIR}/venv"
LOG="${SCRIPT_DIR}/llama_server.log"

# ── Colour helpers ────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[start.sh]${NC} $*"; }
warn()  { echo -e "${YELLOW}[start.sh]${NC} $*"; }
error() { echo -e "${RED}[start.sh]${NC} $*"; }

# ── Preflight checks ──────────────────────────────────────────────────────────
if [ ! -f "${LLAMA_SERVER}" ]; then
    error "llama-server not found at ${LLAMA_SERVER}"
    error "Build llama.cpp first: cd ~/llama.cpp && cmake -B build && cmake --build build"
    exit 1
fi

if [ ! -f "${MODEL}" ]; then
    error "Model not found at ${MODEL}"
    exit 1
fi

# ── Kill any existing llama-server ────────────────────────────────────────────
if pgrep -x llama-server > /dev/null 2>&1; then
    warn "Stopping existing llama-server...";
    pkill -x llama-server || true
    sleep 1
fi

# ── Start llama-server ────────────────────────────────────────────────────────
info "Starting llama-server with Llama-3.2-1B ..."
info "  Model : ${MODEL}"
info "  Port  : 8080"
info "  Log   : ${LOG}"

# -c 2048   : context window (1B model — keep small for speed)
# -t 4      : threads (Pi 4 has 4 cores)
# --no-mmap : avoids memory fragmentation on Pi
# -ngl 0    : no GPU layers (Pi has no CUDA)
nohup "${LLAMA_SERVER}" \
    --model "${MODEL}" \
    --host 127.0.0.1 \
    --port 8080 \
    -c 512 \
    -t 3 \
    -b 128 \
    --temp 0 \
    --top-k 1 \
    --top-p 0.1 \
    --repeat-penalty 1.05 \
     \
    -ngl 0 \
    > "${LOG}" 2>&1 &

LLAMA_PID=$!
info "llama-server PID: ${LLAMA_PID}"

# ── Wait for llama-server to be ready (up to 120 s) ──────────────────────────
info "Waiting for llama-server to be ready..."
TIMEOUT=120
ELAPSED=0
while true; do
    if curl -sf http://127.0.0.1:8080/health > /dev/null 2>&1; then
        info "llama-server is ready! (${ELAPSED}s)";
        break
    fi
    if ! kill -0 "${LLAMA_PID}" 2>/dev/null; then
        error "llama-server crashed — check ${LOG}"
        exit 1
    fi
    if [ "${ELAPSED}" -ge "${TIMEOUT}" ]; then
        warn "llama-server not ready after ${TIMEOUT}s — continuing anyway (it may still be loading)"
        break
    fi
    sleep 2
    ELAPSED=$((ELAPSED + 2))
    echo -n "."
done
echo

# ── Activate Python venv and launch main.py ───────────────────────────────────
info "Activating venv: ${VENV}"
# shellcheck disable=SC1091
source "${VENV}/bin/activate"

info "Launching main.py ..."
echo "======================================"
cd "${SCRIPT_DIR}"
exec python3 main.py
