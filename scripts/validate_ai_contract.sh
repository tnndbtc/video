#!/usr/bin/env bash
# AI plan schema contract tests + optional OpenAI E2E round-trip.
# Usage:
#   ./scripts/validate_ai_contract.sh                          # contract tests only
#   RUN_OPENAI_ROUNDTRIP=1 ./scripts/validate_ai_contract.sh  # + full E2E (stub planner)
#   OPENAI_API_KEY=sk-... ./scripts/validate_ai_contract.sh   # + full E2E (real OpenAI)
#   API_BASE_URL=http://localhost:8080 PROMPT="..." OPENAI_API_KEY=... ./scripts/validate_ai_contract.sh

set -euo pipefail
cd "$(dirname "$0")/.."

API_BASE_URL="${API_BASE_URL:-http://localhost:8080}"
PROMPT="${PROMPT:-Generate a short energetic montage from all available clips}"
ARTIFACTS="/tmp/video_validate"
PASS_COUNT=0
FAIL_COUNT=0

_pass() { echo "  ✅ $1"; PASS_COUNT=$((PASS_COUNT+1)); }
_fail() { echo "  ❌ $1"; FAIL_COUNT=$((FAIL_COUNT+1)); }
_info() { echo "  ℹ  $1"; }

# ─────────────────────────────────────────────────────────
# Section 0: Preconditions
# ─────────────────────────────────────────────────────────
echo ""
echo "=== Section 0: Preconditions ==="

for cmd in python3 curl; do
  if command -v "$cmd" &>/dev/null; then _pass "$cmd found"
  else _fail "$cmd not found"; fi
done

# ffprobe only required for E2E section; warn here, fail later if needed
if command -v ffprobe &>/dev/null; then _pass "ffprobe found"
else _info "ffprobe not found (only needed for E2E round-trip)"; fi

# ─────────────────────────────────────────────────────────
# Section 1: pytest contract tests (always runs)
# ─────────────────────────────────────────────────────────
echo ""
echo "=== Section 1: Contract Tests (pytest) ==="

if python3 -m pytest backend/tests/integration/test_ai_endpoints.py \
                      backend/tests/unit/test_edit_plan.py \
    -q --tb=short 2>&1; then
  _pass "Contract tests"
else
  _fail "Contract tests"
fi

# ─────────────────────────────────────────────────────────
# Section 2: Optional E2E round-trip
# Triggered when: OPENAI_API_KEY is set  OR  RUN_OPENAI_ROUNDTRIP=1
# ─────────────────────────────────────────────────────────
RUN_E2E=0
[[ -n "${OPENAI_API_KEY:-}" ]] && RUN_E2E=1
[[ "${RUN_OPENAI_ROUNDTRIP:-0}" == "1" ]] && RUN_E2E=1

if [[ "$RUN_E2E" == "0" ]]; then
  echo ""
  echo "=== Section 2: E2E Round-Trip (SKIPPED — set OPENAI_API_KEY or RUN_OPENAI_ROUNDTRIP=1) ==="
else
  echo ""
  echo "=== Section 2: E2E Round-Trip (API_BASE_URL=$API_BASE_URL) ==="
  mkdir -p "$ARTIFACTS"

  # ── 2.0 Server reachability ──────────────────────────────
  if curl -sf --max-time 10 "$API_BASE_URL/health" >/dev/null 2>&1; then
    _pass "Backend reachable at $API_BASE_URL"
  else
    _fail "Backend not reachable at $API_BASE_URL (is the server running?)"
    # Hard stop — rest of section is meaningless
    echo ""
    echo "=== SUMMARY ==="
    echo "PASS: $PASS_COUNT  FAIL: $FAIL_COUNT"
    [[ $FAIL_COUNT -eq 0 ]] && exit 0 || exit 1
  fi

  # ── 2.1 Auth: register + login ───────────────────────────
  TS=$(date +%s)
  USERNAME="validate_${TS}"
  PASSWORD="ValidatePass1!"

  curl -sf --max-time 15 -X POST "$API_BASE_URL/api/auth/register" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}" >/dev/null

  TOKEN=$(curl -sf --max-time 15 -X POST "$API_BASE_URL/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

  [[ -n "$TOKEN" ]] && _pass "Auth token acquired" || { _fail "Auth failed"; exit 1; }

  # ── 2.2 Create project ───────────────────────────────────
  PROJECT_ID=$(curl -sf --max-time 15 -X POST "$API_BASE_URL/api/projects" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"E2E Validate $TS\"}" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

  [[ -n "$PROJECT_ID" ]] && _pass "Project created: $PROJECT_ID" || { _fail "Project creation failed"; exit 1; }

  # ── 2.3 Generate + upload test media ─────────────────────
  # Generate 2 small test JPEG images via ffmpeg (fast, no dependencies)
  # Endpoint: POST /api/projects/{id}/media (multipart, field name "files")
  # Response: {"total_uploaded": N, "uploaded": [...], "failed": [...]}
  for i in 1 2; do
    IMG="$ARTIFACTS/test_img_${i}.jpg"
    ffmpeg -y -f lavfi -i "color=c=blue:size=640x480:d=1" \
      -frames:v 1 "$IMG" -loglevel quiet 2>/dev/null \
      || python3 scripts/generate_test_media.py --type image --out "$IMG" 2>/dev/null
    UPLOAD_RESP=$(curl -sf --max-time 30 -X POST "$API_BASE_URL/api/projects/$PROJECT_ID/media" \
      -H "Authorization: Bearer $TOKEN" \
      -F "files=@$IMG;type=image/jpeg")
    ASSET_ID=$(echo "$UPLOAD_RESP" | python3 -c "
import sys,json; r=json.load(sys.stdin)
print(r['uploaded'][0]['id'])
")
    [[ -n "$ASSET_ID" ]] && _pass "Media asset $i uploaded: $ASSET_ID" \
      || _fail "Media upload $i failed"
  done

  # ── 2.4 Generate + apply plan (plan_and_apply) ───────────
  PLAN_FILE="$ARTIFACTS/plan.json"
  PLAN_RESPONSE=$(curl -sf --max-time 60 -X POST "$API_BASE_URL/api/ai/plan_and_apply" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"project_id\":\"$PROJECT_ID\",\"prompt\":\"$PROMPT\"}")

  echo "$PLAN_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d.get('edit_plan',{}), indent=2))" > "$PLAN_FILE"

  if echo "$PLAN_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('ok')==True"; then
    _pass "plan_and_apply returned ok=true"
  else
    _fail "plan_and_apply failed"
  fi

  # ── 2.5 Validate plan schema (reuse existing validator) ──
  if python3 -c "
import json, sys
sys.path.insert(0, 'backend')
from app.schemas.edit_plan import EditPlanV1
plan = json.load(open('$PLAN_FILE'))
EditPlanV1.model_validate(plan)
" 2>&1; then
    _pass "EditPlanV1 schema validation passed"
  else
    _fail "EditPlanV1 schema validation failed"
  fi

  # ── 2.6 Trigger render ───────────────────────────────────
  RENDER_RESP=$(curl -sf --max-time 30 -X POST "$API_BASE_URL/api/projects/$PROJECT_ID/render" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"type":"final"}')
  RENDER_STATUS=$(echo "$RENDER_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))")
  [[ "$RENDER_STATUS" == "queued" || "$RENDER_STATUS" == "running" ]] \
    && _pass "Render job queued (status=$RENDER_STATUS)" \
    || _fail "Render job status unexpected: $RENDER_STATUS"

  # ── 2.7 Poll render status (120s timeout) ────────────────
  POLL_MAX=24   # 24 × 5s = 120s
  POLL=0
  FINAL_STATUS="unknown"
  while [[ $POLL -lt $POLL_MAX ]]; do
    sleep 5
    FINAL_STATUS=$(curl -sf --max-time 10 "$API_BASE_URL/api/projects/$PROJECT_ID/render/final/status" \
      -H "Authorization: Bearer $TOKEN" \
      | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))")
    _info "Poll $((POLL+1))/$POLL_MAX: render status=$FINAL_STATUS"
    [[ "$FINAL_STATUS" == "complete" || "$FINAL_STATUS" == "failed" ]] && break
    POLL=$((POLL+1))
  done

  if [[ "$FINAL_STATUS" == "complete" ]]; then
    _pass "Render completed"
  else
    _fail "Render did not complete (final status=$FINAL_STATUS)"
  fi

  # ── 2.8 Download and verify output MP4 ───────────────────
  OUTPUT_MP4="$ARTIFACTS/output.mp4"
  curl -sf --max-time 60 "$API_BASE_URL/api/projects/$PROJECT_ID/render/final/download" \
    -H "Authorization: Bearer $TOKEN" \
    -o "$OUTPUT_MP4"

  if [[ -s "$OUTPUT_MP4" ]]; then
    _pass "MP4 downloaded: $OUTPUT_MP4 ($(du -h "$OUTPUT_MP4" | cut -f1))"
  else
    _fail "MP4 download failed or empty"
  fi

  if command -v ffprobe &>/dev/null; then
    DURATION=$(ffprobe -v quiet -print_format json -show_format "$OUTPUT_MP4" \
      | python3 -c "import sys,json; print(json.load(sys.stdin)['format']['duration'])" 2>/dev/null || echo "0")
    if python3 -c "assert float('${DURATION:-0}') > 0" 2>/dev/null; then
      _pass "ffprobe: duration=${DURATION}s"
    else
      _fail "ffprobe: duration invalid or zero"
    fi
  else
    _info "ffprobe not available — skipping duration check"
  fi

  _info "Artifacts saved to: $ARTIFACTS/"
  _info "  plan.json    — validated EditPlanV1 JSON"
  _info "  output.mp4   — rendered video"
fi

# ─────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────
echo ""
echo "=== SUMMARY ==="
echo "PASS: $PASS_COUNT  FAIL: $FAIL_COUNT"
[[ $FAIL_COUNT -eq 0 ]] && { echo "PASS"; exit 0; } || { echo "FAIL"; exit 1; }
