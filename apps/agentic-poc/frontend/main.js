const apiBase = "http://127.0.0.1:8000";
const timeline = document.getElementById("timeline");
const tracePanel = document.getElementById("tracePanel");
const statusEl = document.getElementById("status");
const sessionInput = document.getElementById("sessionId");
const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("message");

function appendMessage(role, content) {
  const p = document.createElement("p");
  p.className = role === "user" ? "msg-user" : "msg-assistant";
  p.textContent = `${role}: ${content}`;
  timeline.appendChild(p);
}

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const session_id = sessionInput.value.trim();
  const message = messageInput.value.trim();
  if (!message) return;

  appendMessage("user", message);
  messageInput.value = "";
  statusEl.textContent = "Running orchestrator...";

  try {
    const response = await fetch(`${apiBase}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id, message }),
    });
    const raw = await response.text();
    let payload;
    try {
      payload = raw ? JSON.parse(raw) : {};
    } catch {
      statusEl.textContent = `Error: HTTP ${response.status} (non-JSON body)`;
      return;
    }
    if (!response.ok) {
      const detail = payload.detail ?? payload.message ?? raw.slice(0, 200);
      statusEl.textContent = `Error: HTTP ${response.status} — ${typeof detail === "string" ? detail : JSON.stringify(detail)}`;
      return;
    }
    appendMessage("assistant", payload.response);
    tracePanel.textContent = JSON.stringify(payload.trace, null, 2);
    statusEl.textContent = "Done";
  } catch (error) {
    statusEl.textContent = `Error: ${error}`;
  }
});

document.getElementById("newSession").addEventListener("click", () => {
  sessionInput.value = `session-${Date.now()}`;
  timeline.innerHTML = "";
  tracePanel.textContent = "";
  statusEl.textContent = "New session created";
});

document.getElementById("clearSession").addEventListener("click", async () => {
  const session_id = sessionInput.value.trim();
  try {
    const response = await fetch(`${apiBase}/sessions/clear`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id }),
    });
    if (!response.ok) {
      statusEl.textContent = `Clear failed: HTTP ${response.status}`;
      return;
    }
  } catch (error) {
    statusEl.textContent = `Clear failed: ${error}`;
    return;
  }
  timeline.innerHTML = "";
  tracePanel.textContent = "";
  statusEl.textContent = "Session history cleared";
});
