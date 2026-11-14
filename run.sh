#!/usr/bin/env bash
# One command: setup (if needed) -> offline tests -> offline evals -> live demo (if a key is set).
# Usage: ./run.sh   (or: make run)   OFFLINE=1 ./run.sh skips the live demo
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3.11}"
BIN=.venv/bin
OUT=out

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

# (Re)build .venv if it is missing or broken (e.g. the folder was moved after setup).
venv_ok() { "$BIN/mindmap" --help >/dev/null 2>&1 && "$BIN/pytest" --version >/dev/null 2>&1; }
if ! venv_ok; then
  step "Setup (.venv with $PYTHON)"
  rm -rf .venv
  make setup PYTHON="$PYTHON"
fi

step "Offline tests (no key, no network)"
make test

step "Pipeline bench (offline, scripted model output)"
"$BIN/mindmap" eval --mode pipeline

step "Replay recorded Gemini run (offline)"
MINDMAP_PROVIDER=gemini "$BIN/mindmap" eval --suite evals --mode replay

# Live demo only when a key is available (shell env or .env).
has_key() {
  [ -n "${GEMINI_API_KEY:-}${GOOGLE_API_KEY:-}${ANTHROPIC_API_KEY:-}" ] && return 0
  [ -f .env ] && grep -Eq '^(GEMINI_API_KEY|GOOGLE_API_KEY|ANTHROPIC_API_KEY)=.+' .env
}

if [ -z "${OFFLINE:-}" ] && has_key; then
  mkdir -p "$OUT"
  step "LIVE: generate a mindmap"
  "$BIN/mindmap" generate --in evals/docs/photosynthesis.txt --out "$OUT/map.json" -v
  step "LIVE: grow it with a second document"
  "$BIN/mindmap" grow --map "$OUT/map.json" --in evals/docs/photosynthesis_part2.txt --out "$OUT/map2.json" -v
  step "Render Mermaid diagram"
  "$BIN/mindmap" render --map "$OUT/map2.json" --out "$OUT/map2.mmd"
  step "Done. Outputs in $OUT/ (paste $OUT/map2.mmd into mermaid.live)"
else
  step "Done (offline only). Add a key to .env (cp .env.example .env) to also run the live demo."
fi
