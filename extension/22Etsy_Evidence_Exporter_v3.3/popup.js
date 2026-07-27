const input = document.getElementById("agent");
const operator = document.getElementById("operator");
const token = document.getElementById("token");
const ok = document.getElementById("ok");
const stUrl = document.getElementById("st-url");
const stToken = document.getElementById("st-token");
const stTest = document.getElementById("st-test");

function refreshStatus() {
  const hasUrl = !!input.value.trim();
  const hasToken = !!token.value.trim();
  stUrl.textContent = hasUrl ? "set ✓" : "not set";
  stUrl.className = hasUrl ? "dot-on" : "dot-off";
  stToken.textContent = hasToken ? "set ✓" : "not set";
  stToken.className = hasToken ? "dot-on" : "dot-off";
}

chrome.storage.local.get({ agentUrl: "", agentToken: "", operator: "" }, (cfg) => {
  input.value = cfg.agentUrl || "";
  token.value = cfg.agentToken || "";
  operator.value = cfg.operator || "";
  refreshStatus();
});

input.addEventListener("input", refreshStatus);
token.addEventListener("input", refreshStatus);

document.getElementById("save").addEventListener("click", () => {
  chrome.storage.local.set(
    { agentUrl: input.value.trim(), agentToken: token.value.trim(),
      operator: operator.value.trim() },
    () => {
      ok.textContent = "Saved.";
      refreshStatus();
      setTimeout(() => (ok.textContent = ""), 1500);
    }
  );
});

// Lightweight reachability check. Sends a zero-row ping through the background
// worker (which only allows /api/import). Reports HTTP status without creating
// real data. The token is never printed.
document.getElementById("test").addEventListener("click", () => {
  const url = input.value.trim();
  if (!url) { stTest.textContent = "set the Agent import URL first"; return; }
  stTest.textContent = "testing…";
  const body = {
    schema_version: "1.1",
    exporter_version: "3.3.0",
    view: "connection-test",
    captured_at: new Date().toISOString(),
    source: "extension-popup",
    source_type: "connection_test",
    evidence_policy: "rendered_page_only_no_invention",
    connection_test: true,
    headers: [],
    rows: []
  };
  chrome.runtime.sendMessage(
    { type: "agent-post", url, token: token.value.trim(), body },
    (r) => {
      if (chrome.runtime.lastError) {
        stTest.textContent = "failed: " + chrome.runtime.lastError.message;
        return;
      }
      if (!r) { stTest.textContent = "no response from worker"; return; }
      if (r.status === 401 || r.status === 403) {
        stTest.textContent = "reached ✓ but token rejected (" + r.status + ")";
      } else if (r.status && r.status > 0) {
        stTest.textContent = "reached ✓ (HTTP " + r.status + ")";
      } else {
        stTest.textContent = "could not reach: " + (r.error || "unknown");
      }
    }
  );
});
