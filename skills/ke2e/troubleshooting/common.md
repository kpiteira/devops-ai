# Troubleshooting: Common Issues

## Cold Start Timeout

**Symptom:** First request takes very long or times out

**Why:** First request on a fresh container may trigger initialization: dependency loading, config reading, warm-up processing. Services backed by LLMs can take 200-400+ seconds for cold start.

**Fixes:**
- Use a session warmup preflight module to absorb cold start cost before timing-sensitive tests
- Set timeout appropriately for cold-start-expected tests (e.g., 600s)
- After first request, subsequent requests should be fast

---

## API Schema Changes

**Symptom:** Test expects a field that doesn't exist, or field has unexpected type

**Why:** API response schema changed since test recipe was written.

**Fixes:**
1. Check current API endpoints in the project source code
2. Update test recipe with correct field names
3. Category: TEST_ISSUE

---

## Container Name Mismatch

**Symptom:** `docker exec` commands fail with "No such container"

**Why:** Container name depends on kinfra slot: `${PROJECT}-slot-{N}-{service}-1`

**Fixes:**
- Always discover container dynamically:
  ```bash
  CONTAINER=$(docker ps --filter "name=${PROJECT}-slot" --format "{{.Names}}" | head -1)
  ```
- Never hardcode container names in test recipes

---

## Port Confusion (Sandbox vs Production)

**Symptom:** Test passes but changes aren't reflected, or test affects production

**Why:** Testing against the production/default port instead of sandbox port

**Fixes:**
- Always set the port variable (from infra.toml) before running tests
- `kinfra status` shows your sandbox port
- Production = default port, sandbox = default + slot_id

---

## Stale State After Code Change

**Symptom:** Test passes but behavior doesn't reflect code changes

**Why:** Container is running the old code. Code changes require container rebuild.

**Fixes:**
1. Rebuild sandbox: `kinfra sandbox start`
2. Wait for container to be healthy
3. First request may be a cold start

---

## Permission Denied in Container

**Symptom:** docker exec commands fail with permission errors

**Why:** File ownership issues inside container (root vs app user)

**Fixes:**
```bash
CONTAINER=$(docker ps --filter "name=${PROJECT}-slot" --format "{{.Names}}" | head -1)
docker exec "$CONTAINER" sh -c "ls -la /path/to/data/"
# If permission issue, container rebuild usually fixes it
kinfra sandbox start
```

---

## Health Check Passes But Feature Broken

**Symptom:** Pre-flight passes, but actual test steps fail

**Why:** Health endpoint only checks basic liveness, not feature-level readiness

**Fixes:**
- Add test-specific pre-flight checks for the feature being tested
- Check dependent services (database, external APIs, message queues)
- Look at container logs: `docker compose logs <service> --tail 30`
