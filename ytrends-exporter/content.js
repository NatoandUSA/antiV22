/* YTrends Exporter v2 - content script.
 *
 * One-click capture of the data ALREADY RENDERED on your screen, as CSV/JSON
 * download or a push to your 22etsy-agent. Read-only: it never clicks, never
 * automates a marketplace, never logs in. Exactly what "Save Page As" captures,
 * minus the manual work.
 *
 * Sources:
 *  - YTrends (trends.ytuong.ai): any data table (keywords, gems, categories...)
 *  - ytuong.me "Hot" listing cards: listing id/title/price + 24h sold/views/favs
 *  - Etsy search results (+ HeyEtsy overlay analytics when the panel is on)
 *  - Pinterest pins (hydration JSON first, DOM fallback)
 *  - Amazon search results: asin/title/price/rating/ratings/bought-per-month
 *  - Alibaba search results: title/price/min-order/sold/supplier/years/verified
 */
(function () {
  "use strict";
  const BTN_ID = "ytx-toolbar";
  const clean = (s) => (s || "").replace(/\s+/g, " ").trim();

  // ---- site detection --------------------------------------------------------
  function isEtsy() { return /(^|\.)etsy\.com$/.test(location.hostname); }
  function isPinterest() { return /(^|\.)pinterest\./.test(location.hostname); }
  function isAmazon() { return /(^|\.)amazon\./.test(location.hostname); }
  function isAlibaba() { return /(^|\.)alibaba\.com$/.test(location.hostname); }
  function isYtuongMe() { return /(^|\.)ytuong\.me$/.test(location.hostname); }

  // ---- generic table extraction (YTrends) ------------------------------------
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
  function extractTable(table) {
    const headEls = table.querySelectorAll("thead th, thead td");
    let headers = Array.from(headEls).map(cellText).filter(Boolean);
    const rows = [];
    for (const tr of table.querySelectorAll("tbody tr")) {
      const cells = Array.from(tr.querySelectorAll("td")).map(cellText);
      if (cells.some((c) => c !== "")) rows.push(cells);
    }
    if (!headers.length && rows.length) headers = rows[0].map((_, i) => "col" + (i + 1));
    return { headers, rows };
  }

  // ---- ytuong.me "Hot" listing cards ----------------------------------------
  function extractYtuongHot() {
    const byId = {};
    for (const a of document.querySelectorAll('a[href*="etsy.com/listing/"]')) {
      const m = (a.getAttribute("href") || "").match(/\/listing\/(\d+)/);
      if (m && !byId[m[1]]) byId[m[1]] = a;
    }
    const headers = ["listing_id", "title", "price_usd", "sold_24h", "views_24h",
      "favorites_24h", "badge", "url"];
    const rows = [];
    for (const id in byId) {
      const a = byId[id];
      const card = a.closest("[wire\\:id]") || a.closest("li") ||
        (a.closest(".relative") && a.closest(".relative").parentElement) ||
        a.parentElement.parentElement || a;
      const T = clean(card.innerText || card.textContent || "");
      const g = (re) => { const m2 = T.match(re); return m2 ? m2[1].replace(/,/g, "") : ""; };
      // title = the longest text line that isn't a pure stat/badge line
      let title = "";
      for (const line of (card.innerText || "").split("\n")) {
        const L = clean(line);
        if (L.length > title.length && L.length > 8 &&
            !/^(hot|popular now|view on etsy|sold|views|favorites)/i.test(L) &&
            !/\d+\s*(usd|sold|views|favorites)/i.test(L)) title = L;
      }
      rows.push([id, title, g(/([\d.,]+)\s*USD/i), g(/([\d,]+)\s*Sold/i),
        g(/([\d,]+)\s*Views?/i), g(/([\d,]+)\s*Favorites?/i),
        /popular now/i.test(T) ? "popular" : (/\bhot\b/i.test(T) ? "hot" : ""),
        "https://www.etsy.com/listing/" + id]);
    }
    return { headers, rows };
  }

  // ---- Amazon search results -------------------------------------------------
  function extractAmazon() {
    const cards = Array.from(document.querySelectorAll(
      '[data-component-type="s-search-result"][data-asin], div.s-result-item[data-asin]'))
      .filter((c) => c.getAttribute("data-asin"));
    const seen = {};
    const headers = ["asin", "title", "price", "list_price", "rating",
      "ratings_count", "bought_past_month", "sponsored", "prime", "url"];
    const rows = [];
    for (const card of cards) {
      const asin = card.getAttribute("data-asin");
      if (!asin || seen[asin]) continue;
      seen[asin] = 1;
      const h2 = card.querySelector("h2");
      const title = clean((h2 && (h2.innerText ||
        (h2.getAttribute("aria-label") || "").replace(/^Sponsored Ad\s*-\s*/i, ""))) || "");
      if (!title) continue;
      const offs = Array.from(card.querySelectorAll(".a-price .a-offscreen"))
        .map((e) => clean(e.textContent)).filter(Boolean);
      const rateEl = card.querySelector(".a-icon-alt");
      const rating = rateEl ? (clean(rateEl.textContent).match(/^[\d.]+/) || [""])[0] : "";
      let ratings = "";
      const rc = card.querySelector('a[aria-label*="ratings" i], a[aria-label*="rating" i]');
      if (rc) ratings = ((rc.getAttribute("aria-label") || "").match(/([\d,]+)/) || ["", ""])[1];
      if (!ratings) {
        const rs = card.querySelector("span.s-underline-text, span.a-size-base.s-underline-text");
        if (rs) ratings = clean(rs.textContent).replace(/[()]/g, "");
      }
      const T = clean(card.innerText || "");
      const bought = (T.match(/([\d.,K+]+)\s*bought in past month/i) || ["", ""])[1];
      const link = card.querySelector('a[href*="/dp/"], h2 a');
      let url = link ? link.href : "";
      const dp = url.match(/\/dp\/([A-Z0-9]{10})/);
      if (dp) url = "https://www.amazon.com/dp/" + dp[1];
      rows.push([asin, title, offs[0] || "", offs[1] || "", rating,
        (ratings || "").replace(/,/g, ""), bought,
        /sponsored/i.test(T) ? "1" : "0",
        card.querySelector(".a-icon-prime") ? "1" : "0", url]);
    }
    return { headers, rows };
  }

  // ---- Alibaba search results ------------------------------------------------
  function extractAlibaba() {
    const byHref = {};
    for (const a of document.querySelectorAll('a[href*="product-detail"]')) {
      const href = (a.href || "").split("?")[0];
      if (!href) continue;
      if (!byHref[href] || clean(a.innerText).length >
          clean(byHref[href].innerText).length) byHref[href] = a;
    }
    const headers = ["title", "price", "min_order", "sold", "supplier",
      "supplier_years", "verified", "url"];
    const rows = [];
    const seenTitle = {};
    for (const href in byHref) {
      const a = byHref[href];
      // climb to a card-sized container (text between 80 and 2000 chars)
      let card = a;
      for (let i = 0; i < 6 && card.parentElement; i++) {
        card = card.parentElement;
        const len = clean(card.innerText || "").length;
        if (len > 120 && len < 2500) break;
      }
      const T = clean(card.innerText || "");
      const img = card.querySelector("img[alt]");
      let title = clean(a.innerText) || clean(img && img.alt) || "";
      if (title.length < 12) {
        // fall back to the longest plausible line in the card
        for (const line of (card.innerText || "").split("\n")) {
          const L = clean(line);
          if (L.length > title.length && L.length > 15 &&
              !/\$|min\. order|sold|yrs|verified|supplier/i.test(L)) title = L;
        }
      }
      if (!title || seenTitle[title.toLowerCase()]) continue;
      seenTitle[title.toLowerCase()] = 1;
      // space-tolerant price parse: Alibaba renders prices from fragment spans, so
      // accept "$ 1 . 85 - $ 3 . 20" and collapse the internal whitespace.
      const priceRaw = (T.match(/\$\s*\d[\d.,\s]*(?:-\s*\$?\s*\d[\d.,\s]*)?/) || [""])[0];
      const price = priceRaw.replace(/\s+/g, "");
      const minOrder = (T.match(/[Mm]in\.?\s*order:?\s*([\d.,]+\s*[a-z]+)/i) || ["", ""])[1];
      const sold = (T.match(/([\d.,]+\+?)\s*sold/i) || ["", ""])[1];
      const yrs = (T.match(/(\d+)\s*yrs?/i) || ["", ""])[1];
      let supplier = "";
      for (const line of (card.innerText || "").split("\n")) {
        const L = clean(line);
        if (/(Co\.,?\s*Ltd|Limited|Factory|Inc\.?$|Exports|Trading|Industry|Technology)/i.test(L)
            && L.length < 80) { supplier = L; break; }
      }
      rows.push([title, price, minOrder, (sold || "").replace(/,/g, ""), supplier,
        yrs, /verified/i.test(T) ? "1" : "0", href]);
    }
    return { headers, rows };
  }

  // ---- Pinterest (hydration JSON first, DOM fallback) ------------------------
  function extractPinterest() {
    const pins = {};
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
          image: imgOf(o), outbound: clean(o.link || rich.url || ""),
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
    for (const a of document.querySelectorAll('a[href*="/pin/"]')) {
      const m = (a.getAttribute("href") || "").match(/\/pin\/(\d+)/);
      if (!m || pins[m[1]]) continue;
      const id = m[1];
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
    return { headers, rows: Object.values(pins).map((p) => headers.map((h) => p[h])) };
  }

  // ---- Etsy search results (+ HeyEtsy overlay) -------------------------------
  function extractEtsy() {
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

  // ---- CSV / naming ----------------------------------------------------------
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

  function sourceTag() {
    if (isPinterest()) return "pinterest";
    if (isEtsy()) return "etsy";
    if (isAmazon()) return "amazon";
    if (isAlibaba()) return "alibaba";
    if (isYtuongMe()) return "ytuongme";
    return "ytrends";
  }

  function viewSlug() {
    const q = new URLSearchParams(location.search).get("q") ||
      new URLSearchParams(location.search).get("k") ||          // amazon uses k=
      new URLSearchParams(location.search).get("SearchText") || // alibaba
      location.pathname.replace(/^\/+|\/+$/g, "");
    const sort = new URLSearchParams(location.search).get("sort");
    const base = (q || sourceTag()).replace(/[^a-z0-9]+/gi, "_").toLowerCase().slice(0, 40);
    return sort ? `${sort}_${base}` : base;
  }

  function today() {
    const d = new Date();
    return d.getFullYear() + "-" +
      String(d.getMonth() + 1).padStart(2, "0") + "-" +
      String(d.getDate()).padStart(2, "0");
  }

  // ---- dispatch --------------------------------------------------------------
  function currentData() {
    let d = null;
    if (isPinterest()) d = extractPinterest();
    else if (isEtsy()) d = extractEtsy();
    else if (isAmazon()) d = extractAmazon();
    else if (isAlibaba()) d = extractAlibaba();
    else {
      const table = pickTable();
      if (table) d = extractTable(table);
      // ytuong.me card pages (Hot / listing grids) have no table -> card extractor
      if ((!d || !d.rows.length) && isYtuongMe()) d = extractYtuongHot();
    }
    return d && d.rows.length ? d : null;
  }

  function payload(data) {
    return {
      view: `${sourceTag()}-${viewSlug()}`, captured_at: new Date().toISOString(),
      source: location.href, headers: data.headers, rows: data.rows
    };
  }

  function download(text, name, mime) {
    const blob = new Blob(["﻿" + text], { type: mime || "text/csv;charset=utf-8" });
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
    flash(`Exported ${data.rows.length} rows (${sourceTag()}).`, true);
  }

  function onJson() {
    const data = currentData();
    if (!data) { flash("No data found on this page.", false); return; }
    download(JSON.stringify(payload(data), null, 1),
      `${sourceTag()}_${viewSlug()}_${today()}.json`, "application/json");
    flash(`Exported ${data.rows.length} rows as JSON.`, true);
  }

  function onSend() {
    const data = currentData();
    if (!data) { flash("No data found on this page.", false); return; }
    chrome.storage.local.get({ agentUrl: "", agentToken: "" }, (cfg) => {
      const url = (cfg.agentUrl || "").trim();
      if (!url) { flash("Set your agent URL in the extension popup first.", false); return; }
      flash("Sending to agent...", null);
      const headers = { "Content-Type": "application/json" };
      if ((cfg.agentToken || "").trim()) headers["X-Import-Token"] = cfg.agentToken.trim();
      fetch(url, { method: "POST", headers, body: JSON.stringify(payload(data)) })
        .then((r) => {
          if (!r.ok) throw new Error("HTTP " + r.status);
          flash(`Sent ${data.rows.length} rows to agent (${sourceTag()}).`, true);
        }).catch((e) => flash("Send failed: " + e.message + " (agent running + CORS on?)", false));
    });
  }

  // ---- UI --------------------------------------------------------------------
  function buildToolbar() {
    if (document.getElementById(BTN_ID)) return;
    const bar = document.createElement("div");
    bar.id = BTN_ID;
    bar.innerHTML =
      '<div class="ytx-row">' +
      '  <span class="ytx-brand">' + sourceTag().toUpperCase() + ' &rarr; agent</span>' +
      '  <button id="ytx-export" class="ytx-btn ytx-primary">CSV</button>' +
      '  <button id="ytx-json" class="ytx-btn">JSON</button>' +
      '  <button id="ytx-send" class="ytx-btn">Send to agent</button>' +
      '  <button id="ytx-hide" class="ytx-x" title="Hide">&times;</button>' +
      '</div><div id="ytx-status" class="ytx-status"></div>';
    document.body.appendChild(bar);
    document.getElementById("ytx-export").addEventListener("click", onExport);
    document.getElementById("ytx-json").addEventListener("click", onJson);
    document.getElementById("ytx-send").addEventListener("click", onSend);
    document.getElementById("ytx-hide").addEventListener("click", () => bar.remove());
    // show what's detected so an empty page is never a silent mystery
    setTimeout(() => {
      const d = currentData();
      flash(d ? `${d.rows.length} rows detected (${sourceTag()}).`
              : "No data detected yet - scroll or wait for the page to load.", d ? true : null);
    }, 800);
  }

  buildToolbar();
  setInterval(buildToolbar, 1500);
})();
