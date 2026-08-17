/* YTrends Exporter - content script.
 *
 * Injects a small toolbar on any YTrends page. On click it reads the CURRENTLY
 * rendered data table (the one you're looking at), turns it into CSV, and either
 * downloads it or POSTs it to your local 22etsy-agent. It never touches Etsy /
 * Amazon and never automates the marketplace - it only reads the DOM already on
 * your screen, exactly what "Save Page As" would capture, minus the manual save.
 */
(function () {
  "use strict";
  const BTN_ID = "ytx-toolbar";

  // ---- table extraction ----------------------------------------------------
  function pickTable() {
    // Prefer the shadcn data table; fall back to the largest <table> on the page.
    let tables = Array.from(document.querySelectorAll('table[data-slot="table"]'));
    if (!tables.length) tables = Array.from(document.querySelectorAll("table"));
    if (!tables.length) return null;
    // choose the table with the most body rows (the main data grid)
    return tables.sort((a, b) =>
      b.querySelectorAll("tbody tr").length - a.querySelectorAll("tbody tr").length)[0];
  }

  function cellText(el) {
    // innerText collapses hidden nodes + respects line breaks; normalise spaces.
    return (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim();
  }

  function extract(table) {
    const headEls = table.querySelectorAll("thead th, thead td");
    let headers = Array.from(headEls).map(cellText).filter(Boolean);
    const bodyRows = Array.from(table.querySelectorAll("tbody tr"));
    const rows = [];
    for (const tr of bodyRows) {
      const cells = Array.from(tr.querySelectorAll("td")).map(cellText);
      if (cells.some((c) => c !== "")) rows.push(cells);
    }
    if (!headers.length && rows.length) headers = rows[0].map((_, i) => "col" + (i + 1));
    return { headers, rows };
  }

  function toCSV({ headers, rows }) {
    const q = (v) => '"' + String(v == null ? "" : v).replace(/"/g, '""') + '"';
    const width = headers.length;
    const lines = [headers.map(q).join(",")];
    for (const r of rows) {
      const padded = r.slice(0, width);
      while (padded.length < width) padded.push("");
      lines.push(padded.map(q).join(","));
    }
    return lines.join("\r\n");
  }

  function viewSlug() {
    const path = location.pathname.replace(/\/en\/?/, "/").replace(/^\/+|\/+$/g, "");
    const sort = new URLSearchParams(location.search).get("sort");
    const base = (path || "ytrends").replace(/[^a-z0-9]+/gi, "_").toLowerCase();
    return sort ? `${sort}_${base}` : base;
  }

  function today() {
    const d = new Date();
    return d.getFullYear() + "-" +
      String(d.getMonth() + 1).padStart(2, "0") + "-" +
      String(d.getDate()).padStart(2, "0");
  }

  // ---- actions -------------------------------------------------------------
  function currentData() {
    const table = pickTable();
    if (!table) return null;
    const data = extract(table);
    return data.rows.length ? data : null;
  }

  function download(csv, name) {
    const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  function flash(msg, ok) {
    const s = document.getElementById("ytx-status");
    if (!s) return;
    s.textContent = msg;
    s.style.color = ok === false ? "#b91c1c" : ok ? "#15803d" : "#555";
  }

  function onExport() {
    const data = currentData();
    if (!data) { flash("No data table found on this page.", false); return; }
    download(toCSV(data), `ytrends_${viewSlug()}_${today()}.csv`);
    flash(`Exported ${data.rows.length} rows.`, true);
  }

  function onSend() {
    const data = currentData();
    if (!data) { flash("No data table found on this page.", false); return; }
    chrome.storage.local.get({ agentUrl: "", agentToken: "" }, (cfg) => {
      const url = (cfg.agentUrl || "").trim();
      if (!url) { flash("Set your agent URL in the extension popup first.", false); return; }
      const token = (cfg.agentToken || "").trim();
      // The agent gates /api/import on this shared secret. Sending a custom
      // header makes the browser preflight (OPTIONS) first; the agent answers it.
      const headers = { "Content-Type": "application/json" };
      if (token) headers["X-Import-Token"] = token;
      flash("Sending to agent...", null);
      fetch(url, {
        method: "POST",
        headers: headers,
        body: JSON.stringify({
          view: viewSlug(), captured_at: new Date().toISOString(),
          source: location.href, headers: data.headers, rows: data.rows
        })
      }).then((r) => {
        if (!r.ok) throw new Error("HTTP " + r.status);
        flash(`Sent ${data.rows.length} rows to agent.`, true);
      }).catch((e) => {
        // 401/503 are token problems, not connectivity — say which.
        const m = String(e.message || "");
        const hint = m.includes("401") ? " — token missing or wrong (check the extension popup vs YTX_IMPORT_TOKEN in .env)"
          : m.includes("503") ? " — the agent has no YTX_IMPORT_TOKEN set in its .env"
          : " (is the agent running + CORS on?)";
        flash("Send failed: " + m + hint, false);
      });
    });
  }

  // ---- UI ------------------------------------------------------------------
  function buildToolbar() {
    if (document.getElementById(BTN_ID)) return;
    const bar = document.createElement("div");
    bar.id = BTN_ID;
    bar.innerHTML =
      '<div class="ytx-row">' +
      '  <span class="ytx-brand">YTrends &rarr; CSV</span>' +
      '  <button id="ytx-export" class="ytx-btn ytx-primary">Export CSV</button>' +
      '  <button id="ytx-send" class="ytx-btn">Send to agent</button>' +
      '  <button id="ytx-hide" class="ytx-x" title="Hide">&times;</button>' +
      '</div><div id="ytx-status" class="ytx-status"></div>';
    document.body.appendChild(bar);
    document.getElementById("ytx-export").addEventListener("click", onExport);
    document.getElementById("ytx-send").addEventListener("click", onSend);
    document.getElementById("ytx-hide").addEventListener("click", () => bar.remove());
  }

  // Keep the toolbar alive across this SPA's route changes / re-renders.
  buildToolbar();
  setInterval(buildToolbar, 1500);
})();
