/* YTrends Exporter - content script.
 * Updated to comprehensively capture HeyEtsy injected data on Etsy search results.
 */
(function () {
  "use strict";
  const BTN_ID = "ytx-toolbar";

  // ---- table extraction ----------------------------------------------------
  function pickTable() {
    let tables = Array.from(document.querySelectorAll('table[data-slot="table"]'));
    if (!tables.length) tables = Array.from(document.querySelectorAll("table"));
    if (!tables.length) return null;
    return tables.sort((a, b) =>
      b.querySelectorAll("tbody tr").length - a.querySelectorAll("tbody tr").length)[0];
  }

  function cellText(el) {
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

  // ---- Etsy search-results extraction (card grid) --------------
  function isEtsy() { return /(^|\.)etsy\.com$/.test(location.hostname); }

  function extractEtsy() {
    const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
    const num = (s) => (s || "").replace(/[^0-9]/g, "");
    const byId = {};
    for (const a of document.querySelectorAll('a[href*="/listing/"]')) {
      const m = (a.getAttribute("href") || "").match(/\/listing\/(\d+)/);
      if (!m) continue;
      const id = m[1];
      if (!byId[id]) byId[id] = a;
      if (a.getAttribute("title") && !byId[id].getAttribute("title")) byId[id] = a;
    }
    
    // Updated headers to include HeyEtsy data
    const headers = ["listing_id", "title", "shop", "price", "price_num",
      "price_was", "reviews", "star_seller", "ad", "bestseller",
      "free_shipping", "url", "he_total_sold", "he_revenue", "he_favorites", "he_created_date"];
      
    const rows = [];
    for (const id in byId) {
      const a = byId[id];
      const scope = a.closest("li") || a.closest("div.v2-listing-card") ||
        a.parentElement || a;
      const h3 = document.getElementById("listing-title-" + id);
      const title = clean(a.getAttribute("title") || (h3 ? h3.textContent : ""));
      if (!title) continue;
      
      const url = (a.href || "").split("?")[0];
      const prices = Array.from(scope.querySelectorAll(".currency-value"))
        .map((e) => clean(e.textContent));
      
      let shop = "";
      const sl = scope.querySelector('a[href*="/shop/"], [data-shop-url]');
      if (sl) {
        const u = sl.getAttribute("href") || sl.getAttribute("data-shop-url") || "";
        const sm = u.match(/\/shop\/([^/?]+)/);
        if (sm) shop = decodeURIComponent(sm[1]);
      }
      if (!shop) {
        const s1 = scope.querySelector('.clickable-shop-name,[data-seller-name-container] span[aria-hidden="true"]');
        if (s1) shop = clean(s1.textContent);
      }
      
      const txt = clean(scope.textContent).toLowerCase();
      const rev = clean(scope.textContent).match(/\(([\d,]+)\)/);

      // --- HEYETSY DATA EXTRACTION ---
      const cardText = clean(scope.textContent);
      
      // 1. Total Sold
      const soldMatch = cardText.match(/([\d,]+\+?)\s*Sold/i);
      const he_total_sold = soldMatch ? soldMatch[1] : "";
      
      // 2. Revenue
      const revMatch = cardText.match(/([\d.]+[KMB]?)\s*USD/i);
      const he_revenue = revMatch ? revMatch[1] : "";
      
      // 3. Created Date
      const createdMatch = cardText.match(/(\d{2}\/\d{2}\/\d{4})/);
      const he_created_date = createdMatch ? createdMatch[1] : "";
      
      // 4. Favorites (Bulletproof chunk isolation)
      let he_favorites = "";
      const favChunkMatch = cardText.match(/Favorites(.*?)Created/i);
      if (favChunkMatch) {
          const numbersInChunk = favChunkMatch[1].match(/[\d,]+/g); 
          if (numbersInChunk && numbersInChunk.length > 0) {
              he_favorites = numbersInChunk[numbersInChunk.length - 1]; 
          }
      }

      rows.push([id, title, shop, prices[0] || "", num(prices[0] || ""),
        prices[1] || "", rev ? rev[1] : "",
        scope.querySelector("[data-star-seller-badge]") ? "1" : "0",
        /ad from shop|ad by/.test(txt) ? "1" : "0",
        /bestseller/.test(txt) ? "1" : "0",
        /free shipping|free delivery/.test(txt) ? "1" : "0", url,
        he_total_sold, he_revenue, he_favorites, he_created_date]);
    }
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
    if (isEtsy()) {
      const q = new URLSearchParams(location.search).get("q") ||
        location.pathname.replace(/^\/+|\/+$/g, "");
      return (q || "search").replace(/[^a-z0-9]+/gi, "_").toLowerCase().slice(0, 40);
    }
    const path = location.pathname.replace(/\/en\/?/, "/").replace(/^\/+|\/+$/g, "");
    const sort = new URLSearchParams(location.search).get("sort");
    const base = (path || "ytrends").replace(/[^a-z0-9]+/gi, "_").toLowerCase();
    return sort ? `${sort}_${base}` : base;
  }

  function sourceTag() { return isEtsy() ? "etsy" : "ytrends"; }

  function today() {
    const d = new Date();
    return d.getFullYear() + "-" +
      String(d.getMonth() + 1).padStart(2, "0") + "-" +
      String(d.getDate()).padStart(2, "0");
  }

  // ---- actions -------------------------------------------------------------
  function currentData() {
    if (isEtsy()) {
      const d = extractEtsy();
      return d.rows.length ? d : null;
    }
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
    if (!data) { flash("No data found on this page.", false); return; }
    download(toCSV(data), `${sourceTag()}_${viewSlug()}_${today()}.csv`);
    flash(`Exported ${data.rows.length} ${isEtsy() ? "listings" : "rows"}.`, true);
  }

  function onSend() {
    const data = currentData();
    if (!data) { flash("No data table found on this page.", false); return; }
    chrome.storage.local.get({ agentUrl: "", agentToken: "" }, (cfg) => {
      const url = (cfg.agentUrl || "").trim();
      if (!url) { flash("Set your agent URL in the extension popup first.", false); return; }
      flash("Sending to agent...", null);
      const headers = { "Content-Type": "application/json" };
      if ((cfg.agentToken || "").trim()) headers["X-Import-Token"] = cfg.agentToken.trim();
      fetch(url, {
        method: "POST",
        headers: headers,
        body: JSON.stringify({
          view: `${sourceTag()}-${viewSlug()}`, captured_at: new Date().toISOString(),
          source: location.href, headers: data.headers, rows: data.rows
        })
      }).then((r) => {
        if (!r.ok) throw new Error("HTTP " + r.status);
        flash(`Sent ${data.rows.length} rows to agent.`, true);
      }).catch((e) => flash("Send failed: " + e.message + " (is the agent running + CORS on?)", false));
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

  buildToolbar();
  setInterval(buildToolbar, 1500);
})();