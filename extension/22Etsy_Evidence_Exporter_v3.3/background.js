/* 22Etsy Evidence Exporter v3.3 - background service worker.
 *
 * Single job: relay a captured-evidence payload to the 22etsy agent's
 * /api/import endpoint. No ChatGPT bridge, no design-result, no image fetch.
 */
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.type !== "agent-post") return;

  const url = String(message.url || "").trim();
  // Production: only the 22etsy agent /api/import endpoint is allowed.
  // Optional dev support: localhost/127.0.0.1 /api/import for local testing.
  const allowed =
    /^https:\/\/etsy\.theglobalserviceteam\.site\/api\/import\/?$/i.test(url) ||
    /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?\/api\/import\/?$/i.test(url);
  if (!allowed) {
    sendResponse({ ok: false, status: 0, error: "Unsupported endpoint — only /api/import is allowed." });
    return;
  }

  const headers = { "Content-Type": "application/json" };
  if (String(message.token || "").trim()) {
    headers["X-Import-Token"] = String(message.token).trim();
  }
  fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify(message.body || {})
  }).then(async (response) => {
    const text = await response.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (e) { /* retain text */ }
    sendResponse({
      ok: response.ok && (!data || data.ok !== false),
      status: response.status,
      data,
      text: data ? "" : text.slice(0, 500)
    });
  }).catch((error) => {
    sendResponse({ ok: false, status: 0, error: error.message });
  });
  return true; // keep the message channel open for the async fetch
});
