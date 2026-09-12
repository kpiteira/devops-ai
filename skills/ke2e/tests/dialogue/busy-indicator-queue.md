# Test: dialogue/busy-indicator-queue

**Purpose:** Validate that when messages arrive via Telegram while the agent session is busy (lock held), a living status message appears, updates with elapsed time and queue count, transitions to "Done" on lock release, and all queued messages are processed in order.
**Duration:** 3-5 minutes (depends on agent processing time for the first message)
**Category:** telegram-ux / busy-indicator

---

## Pre-Flight Checks

**Required modules:**
- [common](../preflight/common.md)

**Test-specific checks:**
- [ ] Telegram adapter is active: `curl -s http://localhost:${API_PORT}/status` returns JSON with `telegram_polling: true` (or equivalent field confirming Telegram polling is alive)
- [ ] Bot token and chat ID are configured: container logs show "Telegram polling started for chat_id=" (check `docker compose logs runtime --since 10m | grep "Telegram polling started"`)
- [ ] Agent runtime is connected: `/status` response includes a session or runtime indicator showing the persistent session is alive

---

## Design Constraints

### Transport Requirement

The busy queue flow ONLY triggers for `transport="telegram"`. The HTTP API endpoints (`/dialogue/message`, `/dialogue/reply`) hardcode `transport="http"` and will fall through to the static busy handler instead of BusyQueue. Therefore, this test MUST send messages through the actual Telegram chat. It cannot be validated purely via HTTP API calls.

### Lock Contention Strategy

To trigger the busy flow, the agent session must be locked by a processing request when subsequent messages arrive. The approach:
1. Send a first message via Telegram that triggers agent processing (acquires the lock)
2. While it's processing (lock held), send additional messages via Telegram
3. Those additional messages hit `TimeoutError` on lock acquisition, entering `_handle_busy_queue_flow`

Sending messages via Telegram Bot API's `sendMessage` to the configured chat is how a human would type -- the bot's polling handler picks it up.

### Telegram Bot API for Verification

Use the Telegram Bot API directly (via curl) to:
- Send messages to the chat (simulating human input)
- Read recent messages via `getUpdates` or by checking chat history
- Verify the bot's status messages by reading them from the chat

---

## Test Data

**First message (trigger lock acquisition):**
```json
{"text": "Summarize what you know about the agent-memory project architecture"}
```

**Follow-up messages (arrive while busy):**
```json
[
  {"text": "Also, what milestones have been completed?"},
  {"text": "And what's the current status of the Telegram integration?"}
]
```

**Why this data:** The first message is open-ended enough to require real LLM processing (10-60s), giving a window to send follow-up messages. The follow-ups are distinct so we can verify each gets a separate response after drain.

---

## Execution Steps

### 0. Capture Baseline State

**Command:**
```bash
# Get the Telegram Bot token and chat ID from the container environment
CONTAINER=$(docker ps --filter "name=agent-memory-slot" --format "{{.Names}}" | head -1)
BOT_TOKEN=$(docker exec "$CONTAINER" sh -c 'echo $TELEGRAM_BOT_TOKEN')
CHAT_ID=$(docker exec "$CONTAINER" sh -c 'echo $TELEGRAM_CHAT_ID')

# Record current message count in chat (for later comparison)
# Use getUpdates to see recent activity
BASELINE=$(curl -s "https://api.telegram.org/bot${BOT_TOKEN}/getUpdates?offset=-1" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('result',[])[0].get('update_id',0) if d.get('result') else 0)")
echo "Baseline update_id: $BASELINE"
```

**Expected:**
- BOT_TOKEN and CHAT_ID are non-empty
- Baseline update_id captured for offset tracking

### 1. Send First Message (Trigger Lock Acquisition)

**Command:**
```bash
# Send a message to the chat as the "human" — this goes through the bot's own sendMessage
# which the polling handler will pick up as an inbound message.
#
# IMPORTANT: We send via Telegram Bot API sendMessage to the chat.
# The bot's dispatcher sees this and routes to dialogue_message().
curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
  -H "Content-Type: application/json" \
  -d "{\"chat_id\": \"${CHAT_ID}\", \"text\": \"Summarize what you know about the agent-memory project architecture\"}"
```

**Expected:**
- HTTP 200 with `"ok": true`
- Message sent to the chat
- Agent begins processing (lock acquired)

**Wait:** 3 seconds (let the agent's polling pick up the message and start processing)

### 2. Send Follow-Up Messages While Busy

**Command:**
```bash
# Send 3 follow-up messages in quick succession while the first is still processing
sleep 3

MSG2=$(curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
  -H "Content-Type: application/json" \
  -d "{\"chat_id\": \"${CHAT_ID}\", \"text\": \"Also, what milestones have been completed?\"}")
echo "MSG2: $MSG2"

sleep 1

MSG3=$(curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
  -H "Content-Type: application/json" \
  -d "{\"chat_id\": \"${CHAT_ID}\", \"text\": \"And what's the current status of Telegram integration?\"}")
echo "MSG3: $MSG3"

sleep 1

MSG4=$(curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
  -H "Content-Type: application/json" \
  -d "{\"chat_id\": \"${CHAT_ID}\", \"text\": \"One more question: how does the belief system work?\"}")
echo "MSG4: $MSG4"
```

**Expected:**
- All 3 messages sent successfully (`"ok": true`)
- Each should trigger a reaction (eyes emoji) from the bot
- A busy status message should appear in the chat: "Got it -- finishing something up"
- As more messages arrive, the status should update to show count: "3 messages queued"

### 3. Wait for Processing to Complete

**Command:**
```bash
# Wait for the agent to finish processing the first message and drain the queue.
# The first message typically takes 10-60s. After lock release, the queue
# drains and processes each follow-up (another 10-60s each).
# Total budget: 5 minutes.
TIMEOUT=300
ELAPSED=0
INTERVAL=10

while [ $ELAPSED -lt $TIMEOUT ]; do
  # Check container logs for evidence of queue drain
  DRAIN_LOG=$(docker compose logs runtime --since 2m 2>/dev/null | grep -c "Processing message.*of" || echo "0")
  DONE_LOG=$(docker compose logs runtime --since 2m 2>/dev/null | grep -c "Done.*reading your messages" || echo "0")

  if [ "$DRAIN_LOG" -gt 0 ] || [ "$DONE_LOG" -gt 0 ]; then
    echo "Queue drain detected at ${ELAPSED}s"
    # Give extra time for all queued messages to be processed
    sleep 30
    break
  fi

  echo "Waiting... (${ELAPSED}s elapsed)"
  sleep $INTERVAL
  ELAPSED=$((ELAPSED + INTERVAL))
done

if [ $ELAPSED -ge $TIMEOUT ]; then
  echo "TIMEOUT: Queue drain not detected within ${TIMEOUT}s"
fi
```

**Expected:**
- Container logs show "Processing message X of Y" entries
- Status message transitions to "Done -- reading your messages now"
- All queued messages get processed

### 4. Verify Status Message Lifecycle in Logs

**Command:**
```bash
# Check container logs for the full busy status lifecycle
echo "=== Busy Status Lifecycle ==="
docker compose logs runtime --since 10m 2>/dev/null | grep -E "(Busy status SENT|edit.*busy|Done.*reading|Processing message|queue timeout)" | tail -20

echo ""
echo "=== Queue Enqueue Events ==="
docker compose logs runtime --since 10m 2>/dev/null | grep -iE "(enqueue|busy.*queue|messages? queued)" | tail -20
```

**Expected:**
- Log line: "Busy status SENT (id=NNN)" -- initial status message created
- Log lines showing status edits with updated count/elapsed time
- Log line: "Processing message 1 of 3", "Processing message 2 of 3", "Processing message 3 of 3"
- No "queue timeout" entries

### 5. Verify Bot Messages in Chat

**Command:**
```bash
# Use Telegram Bot API to check recent messages in the chat.
# getUpdates shows messages the bot received, but we need the bot's own
# sent messages. Use getChat + getChatHistory isn't available via Bot API.
# Instead, verify from container logs that specific messages were sent/edited.

echo "=== Bot Message Activity ==="
docker compose logs runtime --since 10m 2>/dev/null | grep -E "(send_message|edit_message|Got it|finishing something|messages queued|Done.*reading)" | tail -30

echo ""
echo "=== Dialogue Results ==="
docker compose logs runtime --since 10m 2>/dev/null | grep -E "dialogue_(message|reply).*result|DialogueTickResult|messages_sent" | tail -20
```

**Expected:**
- Evidence of "Got it -- finishing something up" being sent
- Evidence of status edits with count ("3 messages queued")
- Evidence of transition message ("Done -- reading your messages now")
- Evidence of responses sent for each queued message (messages_sent > 0)

### 6. Verify Cost (Real LLM Calls)

**Command:**
```bash
# Check that real LLM calls happened (not cached/mocked)
curl -s http://localhost:${API_PORT}/status \
  -H "Authorization: Bearer ${AGENT_MEMORY_AUTH_TOKEN}" | \
  python3 -c "
import sys, json
data = json.load(sys.stdin)
cost = data.get('cost', {})
print(f'Total cost: \${cost.get(\"total_usd\", 0):.4f}')
print(f'Dialogue cost entries: {cost.get(\"entries\", [])}')
"
```

**Expected:**
- cost_usd > 0 (proves real LLM processing occurred for queued messages)

---

## Success Criteria

- [ ] First message triggers agent processing (lock acquired, response eventually sent)
- [ ] Follow-up messages while busy produce a living status message in the chat
- [ ] Container logs confirm BusyQueue enqueue events for each follow-up message
- [ ] Container logs confirm status message was sent ("Busy status SENT")
- [ ] Container logs confirm queue drain with "Processing message X of Y" entries
- [ ] Container logs confirm transition message ("Done -- reading your messages now")
- [ ] All queued messages receive responses (each triggers a dialogue_message or dialogue_reply call)
- [ ] No timeout errors in logs ("queue timeout" absent)

---

## Sanity Checks

**CRITICAL:** These catch false positives

- [ ] `cost_usd > 0` — proves real LLM calls happened, not short-circuited or cached
- [ ] At least 2 "Processing message" log lines — proves multiple messages were actually queued and drained (not just 1)
- [ ] "Busy status SENT" appears in logs — proves BusyQueue path was taken (not the static busy handler fallback)
- [ ] Response time for first message > 5s — proves the agent actually did work (not instant return)
- [ ] No "Session busy during.*http transport" in logs — confirms the Telegram transport path was used, not the HTTP fallback

---

## Troubleshooting

**If no "Busy status SENT" appears in logs:**
- **Cause:** Follow-up messages arrived after the lock was already released (first message processed too fast), or the bot's Telegram polling didn't pick up messages
- **Category:** TEST_ISSUE
- **Cure:** Use a more complex first message that takes longer to process, or reduce the delay before sending follow-ups. Check that Telegram polling is active (`telegram_polling` in /status).

**If "Session busy during message (http transport)" appears:**
- **Cause:** Messages are being routed through the HTTP API endpoint instead of Telegram polling. The sendMessage approach may not be working as expected.
- **Category:** TEST_ISSUE
- **Cure:** Verify that the bot's polling handler is active and picks up messages sent to the chat. The bot only processes messages from the authorized chat_id.

**If queue drain never completes (timeout):**
- **Cause:** The persistent session may have crashed, the lock may never release, or wait_for_lock_release event is not being signaled.
- **Category:** CODE_BUG
- **Cure:** Check container logs for exceptions in the runtime. Look for "lock_released.set()" being called. Verify ClaudePersistentRuntime session is alive.

**If follow-up messages don't get responses:**
- **Cause:** Queue drain processes messages but dialogue_message/dialogue_reply fails for the queued messages (second lock acquisition timeout).
- **Category:** CODE_BUG
- **Cure:** Check if the queued message processing re-enters the busy flow (recursive busy). The lock should be free by the time drain processes.

**If Telegram sendMessage returns error for human-simulated messages:**
- **Cause:** The bot cannot send messages to itself as a "human" -- Bot API sendMessage sends AS the bot, which the polling handler may ignore or not see as a user message.
- **Category:** TEST_ISSUE
- **Cure:** This is a fundamental limitation. The bot's polling only sees messages from users, not from itself. You must send the test messages from a different account or use the `/dialogue/message` API endpoint with a modified transport parameter. See "Alternative Approach" in Notes.

---

## Evidence to Capture

- Container logs (full): `docker compose logs runtime --since 10m 2>/dev/null`
- Status response: `curl -s http://localhost:${API_PORT}/status -H "Authorization: Bearer ${AGENT_MEMORY_AUTH_TOKEN}"`
- BusyQueue-specific logs: `docker compose logs runtime --since 10m 2>/dev/null | grep -iE "(busy|queue|drain|processing message)"`
- Delivery tracker state: `docker exec $CONTAINER sh -c "cat /root/.kagents/lux/body/comm/delivery.jsonl" | tail -20`

---

## Notes

### Bot-to-Self Message Limitation

The primary risk with this test design is that Telegram Bot API `sendMessage` sends messages FROM the bot. The aiogram dispatcher's polling may or may not pick up the bot's own messages as inbound user messages. If the bot filters by user ID and rejects its own messages, this approach will not work.

**Alternative Approach (if bot-to-self doesn't work):**

1. **Manual trigger:** Have Karl send test messages from the Telegram app manually while the test runner monitors logs. This makes the test semi-automated.

2. **API with transport override:** If the `/dialogue/message` endpoint accepted a `transport` query parameter, we could force the Telegram path via HTTP. This would require a small code change (adding `transport: str = "http"` to the request body).

3. **Direct lock simulation:** Use a dedicated test endpoint (e.g., `POST /debug/hold-lock?seconds=30`) that holds the session lock for a fixed time, then send messages via `/dialogue/message` with Telegram transport. This separates the "create contention" concern from the "send message" concern.

The runner should attempt the bot-to-self approach first. If "Busy status SENT" never appears in logs, fall back to noting this as a TEST_ISSUE and recommend the API transport override approach.

### 15-Minute Timeout (Requirement 3)

The 15-minute timeout safety net (`_BUSY_TIMEOUT_SECONDS = 15 * 60`) is NOT tested in this E2E recipe. Testing it would require holding the lock for 15+ minutes, which is impractical and expensive. This is covered by unit tests that mock `wait_for_lock_release` to return `False` and verify the error status message ("Something may have gone wrong") is sent. The E2E test verifies the HAPPY PATH only.

### Port and Auth

- `API_PORT` from `.devops-ai/infra.toml`: sandbox port `7437` (actual = base + slot_id)
- Auth token: `AGENT_MEMORY_AUTH_TOKEN` env var (injected via 1Password in sandbox)
- Telegram secrets: `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` (injected via 1Password)

### Cleanup

After the test completes, the test messages remain in the Telegram chat. No automated cleanup is performed -- the messages serve as visual evidence. If cleanup is desired, use:
```bash
# Delete specific messages by ID (captured during send)
curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/deleteMessage" \
  -H "Content-Type: application/json" \
  -d "{\"chat_id\": \"${CHAT_ID}\", \"message_id\": MSG_ID}"
```
