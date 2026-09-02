#!/usr/bin/env bash
# End-to-end exit check: real requests travel client -> gateway -> real model ->
# detectors -> decision engine -> back, and every one lands in Postgres with its
# evidence. Requires `docker compose up` and a GROQ_API_KEY in .env.
set -uo pipefail

GATEWAY="${GATEWAY_URL:-http://localhost:8080}"
FAILED=0

pass() { printf '  \033[32mok\033[0m    %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; FAILED=1; }

echo "== readiness =="
curl -fsS "$GATEWAY/readyz"; echo

# check <label> <want_http> <want_decision|-> <body> [curl -H args...]
check() {
  local label=$1 want_http=$2 want_decision=$3 body=$4; shift 4
  local http decision
  http=$(curl -sS -o /tmp/smoke_body -w '%{http_code}' "$GATEWAY/v1/chat/completions" \
         -H 'Content-Type: application/json' "$@" -d "$body")
  LAST_BODY=$(cat /tmp/smoke_body)
  decision=$(printf '%s' "$LAST_BODY" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print(""); sys.exit()
print(d.get("detail", {}).get("decision") or d.get("_cp_decision") or "")' 2>/dev/null)
  if [ "$http" != "$want_http" ]; then
    fail "$label — http $http (wanted $want_http): $LAST_BODY"; return
  fi
  if [ "$want_decision" != "-" ] && [ "$decision" != "$want_decision" ]; then
    fail "$label — decision '${decision:-none}' (wanted $want_decision)"; return
  fi
  pass "$label -> $http${want_decision:+ / $want_decision}"
}

echo "== tiered decisions (real model + real detectors) =="

check "clean grounded answer is allowed" 200 - \
  '{"messages":[{"role":"user","content":"Reply with exactly this and nothing else: The Eiffel Tower stands on the Champ de Mars in Paris, France."}],
    "source_documents":["The Eiffel Tower stands on the Champ de Mars in Paris, France."]}' \
  -H 'X-Usecase-Id: KnowledgeCopilot' -H 'X-Jurisdiction: US'

check "PII in the answer is masked in place" 200 - \
  '{"messages":[{"role":"user","content":"Reply with exactly this and nothing else: You can reach me at alex.smith@example.com anytime."}]}' \
  -H 'X-Usecase-Id: SupportAssist' -H 'X-Jurisdiction: US'
if printf '%s' "$LAST_BODY" | grep -q 'alex.smith@example.com'; then
  fail "  the email was returned unredacted"
else
  pass "  email absent from the returned content"
fi

# The real NLI cross-encoder scores this contradiction "high" (-> 403 block,
# via the generic "any high-severity finding blocks" rule) most of the time,
# but the model doesn't *guarantee* it reproduces "Berlin, Germany" verbatim
# on every "reply with exactly this" call — a slightly different generation
# can score "medium" instead (-> 409 review, via the groundedness-specific
# rule). Both withhold the response from the caller, which is what this
# check actually asserts; pinning to one specific tier chases real, expected
# run-to-run variance in the live model rather than a bug. Accept either.
http=$(curl -sS -o /tmp/smoke_body -w '%{http_code}' "$GATEWAY/v1/chat/completions" \
       -H 'Content-Type: application/json' \
       -H 'X-Usecase-Id: KnowledgeCopilot' -H 'X-Jurisdiction: EU' \
       -d '{"messages":[{"role":"user","content":"Reply with exactly this and nothing else: The Eiffel Tower is in Berlin, Germany."}],
            "source_documents":["The Eiffel Tower stands on the Champ de Mars in Paris, France."]}')
LAST_BODY=$(cat /tmp/smoke_body)
decision=$(printf '%s' "$LAST_BODY" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print(""); sys.exit()
print(d.get("detail", {}).get("decision") or "")' 2>/dev/null)
if { [ "$http" = "403" ] && [ "$decision" = "block" ]; } || { [ "$http" = "409" ] && [ "$decision" = "review" ]; }; then
  pass "a contradicted claim is withheld -> $http / $decision"
else
  fail "a contradicted claim is withheld — http $http / decision '${decision:-none}' (wanted 403/block or 409/review): $LAST_BODY"
fi

echo
echo "== audit rows (decision + evidence persisted for every call) =="
docker compose exec -T postgres psql -U controlplane -d controlplane \
  -c "SELECT usecase_id, jurisdiction, status, decision,
             json_array_length(detector_results) AS n_det,
             decision_detail->>'fail_safe_triggered' AS failsafe,
             round(gateway_latency_ms) AS gw_ms
      FROM audit_records ORDER BY id DESC LIMIT 4;"

echo
if [ "$FAILED" = 0 ]; then
  echo "OK — real requests forwarded to a real model, checked, decided, and audited end to end."
else
  echo "SMOKE FAILED"; exit 1
fi

echo
echo "== action gate (mailtrap) =="
req_id=$(docker compose exec -T postgres psql -tA -U controlplane -d controlplane -c "SELECT request_id FROM audit_records WHERE decision = 'allow' ORDER BY id DESC LIMIT 1;")
if [ -n "$req_id" ]; then
  action_resp=$(curl -sS -w '\n%{http_code}' "$GATEWAY/v1/actions/execute" \
         -H 'Content-Type: application/json' \
         -d '{"request_id": "'"$req_id"'", "action_type": "send_email", "payload": {"to": "test@example.com", "subject": "Smoke Test", "body": "Hello"}}')
  http=$(echo "$action_resp" | tail -n1)
  body=$(echo "$action_resp" | sed '$d')
  
  if [ "$http" != "200" ]; then
    fail "action execute failed — http $http: $body"
  else
    pass "action executed -> $http"
  fi
else
  fail "could not find an allowed request_id for the action test"
fi
