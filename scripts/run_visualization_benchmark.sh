#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${1:-3001}"
HOST="${HOST:-127.0.0.1}"

echo "Generating visualization benchmark graph..."
python3 "$ROOT_DIR/scripts/generate_visualization_benchmark.py"

echo
echo "Starting HeyBlog frontend benchmark server..."
echo "Benchmark URL: http://$HOST:$PORT/visualization/benchmark"
echo "Stop server: Ctrl+C"
echo

cd "$ROOT_DIR/frontend"
npm run dev -- --host "$HOST" --port "$PORT"
