# Pre-Flight: Common Checks

**Used by:** All E2E tests
**Purpose:** Verify basic environment is healthy before running any test

---

## Configuration Discovery

Before running checks, read the project's `.devops-ai/infra.toml` to determine:

- **Port variable name:** `[sandbox.health].port_var` (e.g., `API_PORT`)
- **Default port:** `[sandbox.ports].<port_var>` (e.g., `8000`)
- **Health endpoint:** `[sandbox.health].endpoint` (e.g., `/health`)
- **Project name:** `[project].name` (e.g., `myproject`)

Use these values in the checks below. Do not hardcode project-specific values.

---

## Checks

### 1. Sandbox Port Detection

**Command:**
```bash
# PORT_VAR and DEFAULT_PORT come from infra.toml
API_PORT=${!PORT_VAR:-$DEFAULT_PORT}

if [ "$API_PORT" = "$DEFAULT_PORT" ] && [ -z "${!PORT_VAR:-}" ]; then
  echo "FAIL: $PORT_VAR not set — refusing to test against production ($DEFAULT_PORT)."
  echo "Set $PORT_VAR to your sandbox port before running tests."
  echo "  Run: kinfra status  # to find your sandbox port"
  exit 1
fi

echo "OK: Using $PORT_VAR=$API_PORT"
```

**Pass if:** Port variable is set to a non-default value (sandbox port = base + slot_id)

**Fail message:** "[PORT_VAR] not set — refusing to test against production"

---

### 2. Docker Container Running

**Command:**
```bash
# PROJECT comes from infra.toml [project].name
CONTAINER=$(docker ps --filter "name=${PROJECT}-slot" --format "{{.Names}}" | head -1)
if [ -z "$CONTAINER" ]; then
  echo "FAIL: No ${PROJECT}-slot container running"
  docker ps --filter "name=${PROJECT}" --format "table {{.Names}}\t{{.Status}}"
  exit 1
fi
echo "OK: Container running: $CONTAINER"
```

**Pass if:** A container matching `${PROJECT}-slot*` is running

**Fail message:** "No ${PROJECT} sandbox container running"

---

### 3. API Health

**Command:**
```bash
# HEALTH_ENDPOINT comes from infra.toml [sandbox.health].endpoint
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  http://localhost:${API_PORT}${HEALTH_ENDPOINT} 2>/dev/null || echo "000")
if [ "$HTTP_CODE" != "200" ]; then
  echo "FAIL: API not responding (HTTP $HTTP_CODE) on port $API_PORT"
  exit 1
fi
echo "OK: API healthy on port $API_PORT"
```

**Pass if:** Health endpoint returns HTTP 200

**Fail message:** "API not responding on port $API_PORT"

---

## Quick Check Script

Run all checks at once (substitute values from infra.toml):

```bash
#!/bin/bash
set -e

# Read these from .devops-ai/infra.toml
PORT_VAR="API_PORT"          # [sandbox.health].port_var
DEFAULT_PORT="8000"          # [sandbox.ports].$PORT_VAR
HEALTH_ENDPOINT="/health"   # [sandbox.health].endpoint
PROJECT="myproject"          # [project].name

API_PORT=${!PORT_VAR:-$DEFAULT_PORT}

echo "=== Pre-Flight: Common Checks ==="

# Check 1: Sandbox port
if [ "$API_PORT" = "$DEFAULT_PORT" ] && [ -z "${!PORT_VAR:-}" ]; then
  echo "FAIL: $PORT_VAR not set or is $DEFAULT_PORT (production). Set it to your sandbox port."
  echo "  Run: kinfra status  # to find your sandbox port"
  exit 1
fi
echo "OK: Using sandbox port $API_PORT"

# Check 2: Docker container
CONTAINER=$(docker ps --filter "name=${PROJECT}-slot" --format "{{.Names}}" | head -1)
if [ -z "$CONTAINER" ]; then
  echo "FAIL: No ${PROJECT} sandbox container running"
  docker ps --filter "name=${PROJECT}" --format "table {{.Names}}\t{{.Status}}"
  exit 1
fi
echo "OK: Container running: $CONTAINER"

# Check 3: API health
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  http://localhost:$API_PORT${HEALTH_ENDPOINT} 2>/dev/null || echo "000")
if [ "$HTTP_CODE" != "200" ]; then
  echo "FAIL: API not responding (HTTP $HTTP_CODE) on port $API_PORT"
  exit 1
fi
echo "OK: API healthy on port $API_PORT"

echo "=== All pre-flight checks passed ==="
```

---

## Symptom -> Cure Mappings

### Container Not Running

**Symptom:** "No ${PROJECT} sandbox container running" or `docker ps` shows no matching containers

**Cause:** Container crashed, not started, or kinfra slot not provisioned

**Cure:**
```bash
kinfra sandbox start
```

**Max Retries:** 2
**Wait After Cure:** 30 seconds (container needs time to start and pass health check)

---

### API Not Responding

**Symptom:** Health check returns non-200 or connection refused

**Cause:** Container starting up, crashed internally, or wrong port

**Cure:**
```bash
CONTAINER=$(docker ps -a --filter "name=${PROJECT}-slot" --format "{{.Names}}" | head -1)
if [ -n "$CONTAINER" ]; then
  docker restart "$CONTAINER"
else
  kinfra sandbox start
fi
```

**Max Retries:** 2
**Wait After Cure:** 15 seconds

---

### Wrong Port (Testing Against Production)

**Symptom:** Port variable not set or equals production default

**Cause:** Environment variable not set, forgot to source sandbox config

**Cure:**
```bash
# Find sandbox port from kinfra
kinfra status
# Look for the port var and export it:
# export PORT_VAR=<sandbox_port>
```

**Max Retries:** 1 (config issue — if this doesn't work, human must intervene)
**Wait After Cure:** 0 seconds (config only, no service restart)
