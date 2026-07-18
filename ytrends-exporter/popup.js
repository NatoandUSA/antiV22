const input = document.getElementById("agent");
const token = document.getElementById("token");
const ok = document.getElementById("ok");

chrome.storage.local.get({ agentUrl: "", agentToken: "" }, (cfg) => {
  input.value = cfg.agentUrl || "";
  token.value = cfg.agentToken || "";
});

document.getElementById("save").addEventListener("click", () => {
  chrome.storage.local.set(
    { agentUrl: input.value.trim(), agentToken: token.value.trim() },
    () => {
      ok.textContent = "Saved.";
      setTimeout(() => (ok.textContent = ""), 1500);
    }
  );
});
