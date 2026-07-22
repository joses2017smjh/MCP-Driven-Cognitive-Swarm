#!/usr/bin/env bash
# Manual capability test — drive every gateway endpoint and check the result.
# Works against any deployment: BASE=https://your-gateway KEY=... ./scripts/smoke_test.sh
set -uo pipefail

BASE="${BASE:-http://localhost:8000}"
KEY="${KEY:-}"          # set to your GATEWAY_API_KEY if the deploy has one
HDR=(-H "Content-Type: application/json")
[[ -n "$KEY" ]] && HDR+=(-H "X-API-Key: $KEY")

pass=0; fail=0
check () { # name  expected-substring  actual
  if grep -q "$2" <<<"$3"; then echo "  PASS  $1"; ((pass++))
  else echo "  FAIL  $1 (wanted '$2')"; echo "        got: ${3:0:200}"; ((fail++)); fi
}

echo "== 1. health (liveness + model version) =="
r=$(curl -s "$BASE/health"); check "health ok" '"ok":true' "$r"; check "model loaded" 'model_version' "$r"

echo "== 2. normal prediction (full layered output) =="
r=$(curl -s -X POST "${HDR[@]}" -d '{"text":"Predict Arsenal vs Man City"}' "$BASE/predict")
check "status complete"   '"status":"complete"'   "$r"
check "outcome probs"     'match_outcome'         "$r"
check "conformal set"     'conformal_set'         "$r"
check "scoreline grid"    'scoreline_grid'        "$r"
check "headline scenario" 'headline_scenario'     "$r"
check "evidence trail"    'tool_calls'            "$r"

echo "== 3. value-bet request → HITL interrupt (no stakes without approval) =="
r=$(curl -s -X POST "${HDR[@]}" -d '{"text":"Arsenal vs Man City — any value bets?"}' "$BASE/predict")
check "pending approval" '"status":"pending_approval"' "$r"
tid=$(grep -o '"thread_id":"[^"]*"' <<<"$r" | head -1 | cut -d'"' -f4)
echo "     thread_id=$tid"

echo "== 4. approve the staking suggestion (resume the interrupt) =="
r=$(curl -s -X POST "${HDR[@]}" -d "{\"thread_id\":\"$tid\",\"action\":\"approve\"}" "$BASE/approve")
check "approved + answer" '"status":"complete"' "$r"
check "stakes disclosed"  'Approved value'      "$r"

echo "== 5. unparseable request → clean 422 (no crash) =="
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "${HDR[@]}" -d '{"text":"hello there"}' "$BASE/predict")
check "422 on gibberish" '422' "$code"

echo "== 6. reflection + rolling calibration =="
curl -s -X POST "${HDR[@]}" -d '{"text":"Predict Arsenal vs Man City"}' "$BASE/predict" >/dev/null
r=$(curl -s -X POST "${HDR[@]}" -d '{"match_id":"ARS-MCI-2026-07-18","actual":"home"}' "$BASE/reflect")
check "reflection settled" 'match_id' "$r"
r=$(curl -s "${HDR[@]}" "$BASE/calibration"); check "calibration report" 'settled' "$r"

echo
echo "== $pass passed, $fail failed =="
exit $((fail > 0))
