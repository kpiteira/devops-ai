# E2E Test Failure Categories

When a test fails, categorize it to guide the main agent's response.

---

## Categories

### ENVIRONMENT

**Definition:** Failure due to infrastructure, not code or configuration.

**Examples:**
- Docker not running or container crashed
- Service not responding after cure attempts
- Network connectivity issues (external APIs, OTEL endpoint)
- Disk space issues in container

**Main Agent Action:** Ask human for help (can't fix via code)

**Report Format:**
```markdown
**Category:** ENVIRONMENT
**Diagnosis:** [Infrastructure issue description]
**Suggested Action:** Manual intervention required. [Specific steps]
```

---

### CONFIGURATION

**Definition:** Failure due to missing env vars, wrong paths, or service config.

**Examples:**
- API key not injected (503 from API)
- Wrong port (testing against production)
- Config file missing required field
- Secret reference not resolving

**Main Agent Action:** Fix configuration, re-run test

**Report Format:**
```markdown
**Category:** CONFIGURATION
**Diagnosis:** [What's misconfigured and why it matters]
**Suggested Action:** [Specific configuration change needed]
```

---

### CODE_BUG

**Definition:** Failure due to bug in implementation code.

**Examples:**
- API returns 500 error
- Exception in service layer (stack trace in logs)
- Wrong status returned from endpoint
- State not written after operation
- Tracking/audit log empty when it should have entries
- Cost/usage tracking shows zero when processing occurred

**Main Agent Action:** Fix code, re-run test

**Report Format:**
```markdown
**Category:** CODE_BUG
**Diagnosis:** [What code is broken and symptoms]
**Suggested Action:** [Where to look, what to fix]
**Evidence:** [Stack traces, error messages, logs]
```

---

### TEST_ISSUE

**Definition:** Failure due to problem with test recipe itself.

**Examples:**
- Test checks wrong endpoint (API changed)
- Success criteria incorrect
- Sanity check threshold too tight
- Test assumes wrong initial state

**Main Agent Action:** Fix test recipe, re-run test

**Report Format:**
```markdown
**Category:** TEST_ISSUE
**Diagnosis:** [What's wrong with the test]
**Suggested Action:** [How to fix the test recipe]
```

---

## Category Decision Tree

```
Test failed
    |
    +-- Pre-flight failed after all cures?
    |       -> ENVIRONMENT
    |
    +-- 503 from API / missing env var?
    |       -> CONFIGURATION
    |
    +-- API error (500) or exception in logs?
    |       -> CODE_BUG
    |
    +-- Test passed but sanity check failed?
    |       |
    |       +-- Zero cost/usage after real processing?
    |       |       -> CODE_BUG (tracking broken)
    |       |
    |       +-- Response time anomaly (instant return)?
    |       |       -> CODE_BUG (request not processed)
    |       |
    |       +-- Audit/state files empty or unchanged?
    |               -> CODE_BUG (persistence broken)
    |
    +-- Test expectations seem wrong?
            -> TEST_ISSUE
```

---

## Common Failure Patterns

| Symptom | Likely Category | Why |
|---------|-----------------|-----|
| Connection refused on port | ENVIRONMENT | Container not running |
| 503 from any endpoint | CONFIGURATION | API key not injected |
| 500 from endpoint | CODE_BUG | Exception in service code |
| State file not found after operation | CODE_BUG | Persistence not working |
| Zero cost after real API call | CODE_BUG | Cost tracking broken |
| Test expects field that doesn't exist | TEST_ISSUE | API schema changed |
| Timeout on cold start | TEST_ISSUE | Timeout too short |
