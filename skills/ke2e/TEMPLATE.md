# Test: {category}/{name}

**Purpose:** [One sentence describing what this test validates — a user scenario, not a technical detail]
**Duration:** [Expected time]
**Category:** [Project-specific category]

---

## Pre-Flight Checks

**Required modules:**
- [common](../preflight/common.md)
- [Add domain-specific if needed]

**Test-specific checks:**
- [ ] [Any checks unique to this test]

---

## Test Data

```json
{
  "REPLACE": "with actual request payload"
}
```

**Why this data:** [Explain parameter choices]

---

## Execution Steps

### 1. [Step Name]

**Command:**
```bash
curl -s -X POST http://localhost:${PORT_VAR}/endpoint \
  -H "Content-Type: application/json" \
  -d '{"key": "value"}'
```

**Expected:**
- [What should happen — describe the user-visible outcome]

### 2. [Next Step]
...

---

## Success Criteria

- [ ] [Observable business outcome 1]
- [ ] [Observable business outcome 2]

---

## Sanity Checks

**CRITICAL:** These catch false positives

- [ ] [Sanity check 1 with threshold — e.g., "cost_usd > 0 proves real processing occurred"]
- [ ] [Sanity check 2 — e.g., "response time > 1s proves request wasn't short-circuited"]

---

## Troubleshooting

**If [symptom]:**
- **Cause:** [Why this happens]
- **Category:** [ENVIRONMENT | CONFIGURATION | CODE_BUG | TEST_ISSUE]
- **Cure:** [How to fix]

---

## Evidence to Capture

- Response body: [Key fields to save]
- Container state: `docker exec $CONTAINER sh -c "[command]"`
- Logs: `docker compose logs <service> --since 5m | grep {pattern}`

---

## Notes

- **Port variable:** Read from `.devops-ai/infra.toml` `[sandbox.health].port_var` — never hardcode ports.
- **Container discovery:** Use `docker ps --filter "name=${PROJECT}-slot" --format "{{.Names}}" | head -1` — never hardcode container names.
- **Non-determinism:** If the service involves LLM calls, assert on structure (fields present, status codes) rather than exact content.
- **Sandbox port:** Always use the port variable from infra.toml — never the production default.
