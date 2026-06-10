#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"

cd "$ROOT_DIR"

echo "=== Frontend Quality Checks ==="
echo ""

# Check node_modules exist
if [ ! -d "$ROOT_DIR/node_modules" ]; then
  echo "[setup] Installing dependencies..."
  npm install
fi

FAILED=0

# Prettier format check
echo "[prettier] Checking formatting..."
if npx prettier --check "$FRONTEND_DIR/**/*.{js,css,html}" 2>&1; then
  echo "[prettier] All files are formatted correctly."
else
  echo ""
  echo "[prettier] FAILED — run 'npm run format' to fix."
  FAILED=1
fi

echo ""

if [ "$FAILED" -eq 0 ]; then
  echo "All checks passed."
else
  echo "One or more checks failed."
  exit 1
fi
