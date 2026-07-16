const input = document.getElementById("agent");
const tokenInput = document.getElementById("token");
const ok = document.getElementById("ok");

chrome.storage.local.get({ agentUrl: "", agentToken: "" }, (cfg) => {
  input.value = cfg.agentUrl || "";
  tokenInput.value = cfg.agentToken || "";
});

document.getElementById("save").addEventListener("click", () => {
  chrome.storage.local.set({
    agentUrl: input.value.trim(),
    agentToken: tokenInput.value.trim(),
  }, () => {
    ok.textContent = "Saved.";
    setTimeout(() => (ok.textContent = ""), 1500);
  });
});
