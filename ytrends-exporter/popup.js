const input = document.getElementById("agent");
const operator = document.getElementById("operator");
const token = document.getElementById("token");
const ok = document.getElementById("ok");

chrome.storage.local.get({ agentUrl: "", agentToken: "", operator: "" }, (cfg) => {
  input.value = cfg.agentUrl || "";
  token.value = cfg.agentToken || "";
  operator.value = cfg.operator || "";
});

document.getElementById("save").addEventListener("click", () => {
  chrome.storage.local.set(
    { agentUrl: input.value.trim(), agentToken: token.value.trim(),
      operator: operator.value.trim() },
    () => {
      ok.textContent = "Saved.";
      setTimeout(() => (ok.textContent = ""), 1500);
    }
  );
});
