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

  // ---- Etsy search-results extraction (card grid, not a table) --------------
  function isEtsy() { return /(^|\.)etsy\.com$/.test(location.hostname); }

  // ---- Pinterest extraction (embedded JSON state first, DOM fallback) -------
  function isPinterest() { return /(^|\.)pinterest\./.test(location.hostname); }

  function extractPinterest() {
    const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
    const pins = {};   // id -> row object

    // 1) Embedded hydration JSON: Pinterest ships pin objects in a <script> blob.
    //    We deep-walk any application/json script and collect objects that look
    //    like a pin (have an id + a save/repin count or a description + image).
    const looksLikePin = (o) => o && typeof o === "object" && o.id &&
      (("repin_count" in o) || ("aggregated_pin_data" in o) ||
       ("description" in o && ("images" in o || "image_large_url" in o)));
    const imgOf = (o) => {
      if (o.image_large_url) return o.image_large_url;
      const im = o.images || {};
      const k = Object.keys(im)[Object.keys(im).length - 1];
      return (im.orig && im.orig.url) || (k && im[k] && im[k].url) || "";
    };
    const walk = (o, depth) => {
      if (!o || typeof o !== "object" || depth > 8) return;
      if (looksLikePin(o) && !pins[o.id]) {
        const rich = o.rich_metadata || o.rich_summary || {};
        pins[o.id] = {
          pin_id: String(o.id),
          title: clean(o.grid_title || o.title || rich.title || ""),
          description: clean(o.description || rich.description || ""),
          saves: (o.repin_count != null ? o.repin_count :
            (o.aggregated_pin_data && o.aggregated_pin_data.aggregated_stats &&
             o.aggregated_pin_data.aggregated_stats.saves) || ""),
          comments: (o.aggregated_pin_data && o.aggregated_pin_data.comment_count) || "",
          image: imgOf(o),
          outbound: clean(o.link || rich.url || ""),
          domain: clean(o.domain || ""),
          pinner: clean((o.pinner && (o.pinner.username || o.pinner.full_name)) || ""),
          board: clean((o.board && o.board.name) || ""),
          is_video: o.is_video ? "1" : "0",
          pin_url: "https://www.pinterest.com/pin/" + o.id + "/",
        };
      }
      const vals = Array.isArray(o) ? o : Object.values(o);
      for (const v of vals) if (v && typeof v === "object") walk(v, depth + 1);
    };
    for (const s of document.querySelectorAll('script[type="application/json"], script#__PWS_INITIAL_PROPS__, script#__PWS_DATA__, script#initial-state')) {
      try { walk(JSON.parse(s.textContent), 0); } catch (e) { /* not json */ }
    }

    // 2) DOM fallback / enrichment for pins loaded on scroll (not in the JSON).
    for (const a of document.querySelectorAll('a[href*="/pin/"]')) {
      const m = (a.getAttribute("href") || "").match(/\/pin\/(\d+)/);
      if (!m) continue;
      const id = m[1];
      if (pins[id]) continue;
      const card = a.closest('[data-test-id="pin"], [data-grid-item], div[role="listitem"]') || a;
      const img = card.querySelector("img");
      const saveEl = card.querySelector('[aria-label*="save" i], [data-test-id="pinrep-reactions"]');
      pins[id] = {
        pin_id: id, title: clean((img && img.alt) || a.getAttribute("aria-label") || ""),
        description: "", saves: saveEl ? clean(saveEl.textContent) : "", comments: "",
        image: (img && (img.src || img.getAttribute("srcset") || "")) || "",
        outbound: "", domain: "", pinner: "", board: "", is_video: "0",
        pin_url: "https://www.pinterest.com/pin/" + id + "/",
      };
    }

    const headers = ["pin_id", "title", "description", "saves", "comments",
      "domain", "pinner", "board", "is_video", "outbound", "image", "pin_url"];
    const rows = Object.values(pins).map((p) => headers.map((h) => p[h]));
    return { headers, rows };
  }

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
    const headers = ["listing_id", "title", "shop", "price", "price_num",
      "price_was", "reviews", "star_seller", "ad", "bestseller", "free_shipping",
      // HeyEtsy / YTuong overlay analytics (only populated when that panel is on)
      "he_sold", "he_views", "he_fav_pct", "he_favorites", "he_created",
      "he_revenue_usd", "he_discount_pct", "he_tags", "url"];
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

      // --- HeyEtsy / YTuong overlay analytics (class-agnostic; read the panel
      //     TEXT so it survives their UI changes). Empty when the overlay is off.
      const T = clean(scope.textContent);
      const g = (re) => { const m = T.match(re); return m ? m[1].replace(/,/g, "") : ""; };
      const he_sold = g(/([\d,]+)\+?\s*Sold/i);
      const he_views = g(/([\d,]+)\+?\s*Views/i);
      const favM = T.match(/Favorites?\s*([\d.]+)%\s*([\d,]+)/i) ||
                   T.match(/([\d.]+)%\s*Favorites?/i);
      const he_fav_pct = favM ? favM[1] : "";
      const he_favorites = (favM && favM[2]) ? favM[2].replace(/,/g, "") : "";
      const he_created = g(/Created\s*([0-9]{1,2}\/[0-9]{1,2}\/[0-9]{4})/i);
      const he_revenue = g(/([\d.]+\s*[KM]?)\s*USD/i);
      const he_off = g(/(\d+)%\s*off/i);
      // HeyEtsy tag chips: the block after a "Tags" label, before "Categories"
      let he_tags = "";
      const tagBlock = T.match(/Tags\s*(?:Copy\s*)?(?:Suggestions\s*)?(.+?)(?:Categories|$)/i);
      if (tagBlock) he_tags = clean(tagBlock[1]).slice(0, 300);

      rows.push([id, title, shop, prices[0] || "", num(prices[0] || ""),
        prices[1] || "", rev ? rev[1] : "",
        scope.querySelector("[data-star-seller-badge]") ? "1" : "0",
        /ad from shop|ad by/.test(txt) ? "1" : "0",
        /bestseller/.test(txt) ? "1" : "0",
        /free shipping|free delivery/.test(txt) ? "1" : "0",
        he_sold, he_views, he_fav_pct, he_favorites, he_created, he_revenue,
        he_off, he_tags, url]);
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
    if (isPinterest()) {
      const q = new URLSearchParams(location.search).get("q") ||
        location.pathname.replace(/^\/+|\/+$/g, "");
      return (q || "pins").replace(/[^a-z0-9]+/gi, "_").toLowerCase().slice(0, 40);
    }
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

  function sourceTag() { return isPinterest() ? "pinterest" : isEtsy() ? "etsy" : "ytrends"; }

  function today() {
    const d = new Date();
    return d.getFullYear() + "-" +
      String(d.getMonth() + 1).padStart(2, "0") + "-" +
      String(d.getDate()).padStart(2, "0");
  }

  // ---- actions -------------------------------------------------------------
  function currentData() {
    if (isPinterest()) {
      const d = extractPinterest();
      return d.rows.length ? d : null;
    }
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

  // Keep the toolbar alive across this SPA's route changes / re-renders.
  buildToolbar();
  setInterval(buildToolbar, 1500);
})();
