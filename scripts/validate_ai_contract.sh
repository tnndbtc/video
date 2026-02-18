#!/usr/bin/env bash
# Runs only the AI plan schema contract tests. Prints PASS/FAIL.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== AI Contract Tests ==="
if python3 -m pytest backend/tests/integration/test_ai_endpoints.py \
                      backend/tests/unit/test_edit_plan.py \
    -q --tb=short 2>&1; then
  echo "PASS"
  exit 0
else
  echo "FAIL"
  exit 1
fi
