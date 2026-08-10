/* 22Etsy Evidence Exporter v3.4.0 - content script.
 *
 * One-click capture of the data ALREADY RENDERED on your screen, as CSV/JSON
 * download or a push to your 22etsy agent (/api/import). Read-only: it never
 * clicks, never automates a marketplace, never logs in. Exactly what
 * "Save Page As" captures, minus the manual work.
 *
 * Design work is NOT handled here. It happens manually inside the 22etsy
 * Design Workspace: you upload the photo + evidence there, copy the prompt to
 * ChatGPT yourself, and paste RESULT_JSON back into 22etsy. This extension only
 * exports evidence.
 *
 * Sources:
 *  - YTrends (trends.ytuong.ai): any data table (keywords, gems, categories...)
 *  - ytuong.me "Hot" listing cards: listing id/title/price + 24h sold/views/favs
 *  - Etsy search results (+ HeyEtsy overlay analytics when the panel is on)
 *  - HeyEtsy /listing/{id} detail pages (single-record analytics)
 *  - Pinterest pins (hydration JSON first, DOM fallback)
 *  - Amazon search results: asin/title/price/rating/ratings/bought-per-month
 *  - Alibaba / AliExpress / 1688 search results: title/price/min-order/sold/...
 */
(function () {
  "use strict";
  const BTN_ID = "ytx-toolbar";
  const clean = (s) => (s || "").replace(/\s+/g, " ").trim();

  // ---- site detection --------------------------------------------------------
  function isEtsy() { return /(^|\.)etsy\.com$/.test(location.hostname); }
  function isHeyEtsy() { return /(^|\.)heyetsy\.com$/.test(location.hostname); }
  function isPinterest() { return /(^|\.)pinterest\./.test(location.hostname); }
  function isAmazon() { return /(^|\.)amazon\./.test(location.hostname); }
  function isAlibaba() { return /(^|\.)alibaba\.com$/.test(location.hostname); }
  function isAliExpress() { return /(^|\.)aliexpress\.(com|us)$/.test(location.hostname); }
  function is1688() { return /(^|\.)1688\.com$/.test(location.hostname); }
  function isYtuongMe() { return /(^|\.)ytuong\.me$/.test(location.hostname); }
  function isHeyEtsyListing() {
    return isHeyEtsy() && /\/listing\/\d+/.test(location.pathname);
  }
  function isEtsyListing() {
    return isEtsy() && /\/listing\/\d+/.test(location.pathname);
  }

  function agentPost(url, token, body, callback) {
    chrome.runtime.sendMessage({
      type: "agent-post", url, token, body
    }, (response) => {
      if (chrome.runtime.lastError) {
        callback({ ok: false, status: 0, error: chrome.runtime.lastError.message });
        return;
      }
      callback(response || { ok: false, status: 0, error: "No response from extension worker" });
    });
  }

  function responseError(r) {
    if (!r) return "No response";
    if (r.error) return r.error;
    const d = r.data || {};
    if (Array.isArray(d.errors)) return d.errors.join("; ");
    return d.error || d.message || r.text || ("HTTP " + (r.status || 0));
  }

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

  // ---- Alibaba / AliExpress / 1688 search results ----------------------------
  function extractAlibaba() {
    const byHref = {};
    for (const a of document.querySelectorAll(
        'a[href*="product-detail"], a[href*="/p-detail/"], a[href*="/item/"], ' +
        'a[href*="/product/"], a[href*="offer/"]')) {
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
      const priceRaw = (T.match(/(?:US\s*)?[$¥₫]\s*\d[\d.,\s]*(?:-\s*(?:US\s*)?[$¥₫]?\s*\d[\d.,\s]*)?/) || [""])[0];
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
    // FULL HeyEtsy overlay capture: lifetime sold + revenue + created/age
    // + views + favorites + conversion + tags + categories - EverBee-grade proof
    // for free. Anchored on the overlay's own label text so numbers never mix.
    const headers = ["listing_id", "title", "shop", "price", "price_num",
      "price_was", "reviews", "star_seller", "ad", "bestseller", "free_shipping",
      "sold_24h", "views_24h", "he_sold", "he_views_avg", "he_views",
      "he_fav_pct", "he_favorites", "he_created", "age_days", "he_updated",
      "he_revenue_usd", "conversion_pct", "country", "shop_daily_sold",
      "he_discount_pct", "he_tags", "he_categories", "url"];
    const AGE = { day: 1, week: 7, month: 30, year: 365 };
    const rows = [];
    for (const id in byId) {
      const a = byId[id];
      const scope = a.closest("li") || a.closest("div.v2-listing-card") ||
        a.parentElement || a;
      const h3 = document.getElementById("listing-title-" + id) ||
        document.getElementById("ad-listing-title-" + id);
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
      if (!shop) {
        const s2 = clean(scope.textContent).match(/By\s+([A-Za-z0-9][\w.-]{2,30})/);
        if (s2) shop = s2[1];
      }
      const txt = clean(scope.textContent).toLowerCase();
      const rev = clean(scope.textContent).match(/\(([\d,]+)\)/);
      // prefer the structured HeyEtsy panel for THIS listing id
      const panel = document.querySelector('[data-heyetsy-listing-id="' + id + '"]');
      const T = clean(((panel || scope).textContent) || "");
      const g = (re) => { const m = T.match(re); return m ? m[1].replace(/,/g, "") : ""; };
      const sold24 = g(/Sold in the Last 24 Hours\D*?([\d,]+)\+?\s*Sold/i);
      const views24 = g(/Views in the Last 24 Hours\D*?([\d,]+)\+?\s*Views/i);
      let soldTotal = g(/Estimated Total Sales\D*?([\d,]+)\+?\s*Sold/i);
      const heRevenue = g(/Estimated Revenue\D*?([\d.,]+\s*[KM]?)\s*USD/i)
        || g(/([\d.,]+\s*[KM]?)\s*USD/i);
      const viewsAvg = g(/([\d,]+)\s*\(Avg\)/i);
      const viewsTotal = g(/Total views of the listing\.?\s*([\d,]+)/i);
      const favPct = g(/favorites per 100 views\.?\s*([\d.]+)\s*%/i)
        || g(/([\d.]+)%\s*Favorites?/i);
      const favTotal = g(/Total number of favorites[^0-9]*([\d,]+)/i);
      const created = g(/Created[^0-9]*?(\d{1,2}\/\d{1,2}\/\d{4})/i);
      let ageDays = "";
      const ageM = T.match(/Created[^(]*\((\d+)\s*(day|week|month|year)s?\)/i);
      if (ageM) ageDays = String(parseInt(ageM[1], 10) * (AGE[ageM[2].toLowerCase()] || 30));
      const updM = T.match(/(?:sold, renewed, or updated\.?|Updated)\s*((?:\d+\s*(?:minute|hour|day|week|month|year)s?\s*ago)|just now)/i);
      const updated = updM ? updM[1] : "";
      const convPct = g(/conversion rate of the listing\.?\s*~?\s*(-?[\d.]+)\s*%/i);
      const ctyM = T.match(/Seller'?s country:\s*([A-Za-z][A-Za-z ,]{1,40})/i);
      const country = ctyM ? clean(ctyM[1]) : "";
      const shopDaily = g(/Recent daily sales of the shop'?s items\.?\D*?([\d,]+)\+?\s*Sold/i);
      const heOff = g(/(\d+)%\s*off/i);
      let tags = "", cats = "";
      if (panel) {
        tags = Array.from(panel.querySelectorAll('a[href*="search?q="]'))
          .map((t) => clean(t.textContent)).filter(Boolean).join("; ");
        const cm = T.match(/Categories\s*(?:Copy\s*)?([A-Za-z].*)$/i);
        if (cm) cats = clean(cm[1]).slice(0, 160);
      }
      if (!tags) {
        const tb = T.match(/Tags\s*(?:Copy\s*)?(?:Suggestions\s*)?(.+?)(?:Categories|$)/i);
        if (tb) tags = clean(tb[1]).slice(0, 400);
      }
      // overlay off -> keep the old loose fallback so plain Etsy still works
      if (!soldTotal && !sold24) soldTotal = g(/([\d,]+)\+?\s*Sold/i);
      rows.push([id, title, shop, prices[0] || "", num(prices[0] || ""),
        prices[1] || "", rev ? rev[1] : "",
        scope.querySelector("[data-star-seller-badge]") ? "1" : "0",
        /ad from shop|ad by/.test(txt) ? "1" : "0",
        /bestseller/.test(txt) ? "1" : "0",
        /free shipping|free delivery/.test(txt) ? "1" : "0",
        sold24, views24, soldTotal, viewsAvg, viewsTotal,
        favPct, favTotal, created, ageDays, updated,
        heRevenue, convPct, country, shopDaily,
        heOff, tags, cats, url]);
    }
    return { headers, rows };
  }

  // ---- Dedicated HeyEtsy listing page ---------------------------------------
  // HeyEtsy /listing/{id} is a single-record analytics page, not a table.
  // Capture only labels and values rendered in the page. Keep raw date/metric
  // strings so the agent can retain provenance and avoid number-format guesses.
  function extractHeyEtsyListing() {
    const idMatch = location.pathname.match(/\/listing\/(\d+)/);
    if (!idMatch) return null;
    const listingId = idMatch[1];
    const T = clean(document.body.innerText || document.body.textContent || "");
    const value = (re) => {
      const m = T.match(re);
      return m ? clean(m[1]).replace(/,/g, "") : "";
    };
    const title = clean(document.querySelector("main h1")?.textContent ||
      document.querySelector("h1")?.textContent ||
      document.title.replace(/^\d+\s*\|\s*/, ""));
    const etsyLink = Array.from(document.querySelectorAll('a[href*="etsy.com/listing/"]'))
      .map((a) => a.href).find((href) => new RegExp("/listing/" + listingId + "(?:/|$)").test(href)) || "";
    const imageCandidates = Array.from(document.querySelectorAll("img, [wire\\:click]"))
      .map((el) => {
        const wire = el.getAttribute && (el.getAttribute("wire:click") || "");
        const wm = wire.match(/https:\/\/i\.etsystatic\.com\/[^'")\s]+/i);
        if (wm) return { url: wm[0], area: 0 };
        const src = el.currentSrc || el.src || "";
        return /^https:\/\/i\.etsystatic\.com\//i.test(src) ? {
          url: src,
          area: Math.max(el.naturalWidth || 0, el.width || 0) *
            Math.max(el.naturalHeight || 0, el.height || 0)
        } : null;
      }).filter(Boolean);
    const imageUrl = imageCandidates
      .sort((a, b) => b.area - a.area)[0]?.url || "";
    const shopLink = document.querySelector('a[href*="heyetsy.com/shop/"]');
    const shop = clean(shopLink?.textContent || "");
    const shopUrl = (shopLink?.href || "").split("?")[0];
    const tagsHeading = Array.from(document.querySelectorAll("h1, h2, h3, h4"))
      .find((el) => clean(el.textContent).toLowerCase() === "tags");
    const tagsContainer = tagsHeading?.closest(".relative, section, article, div") || null;
    const tagsButton = tagsContainer && Array.from(tagsContainer.querySelectorAll("button"))
      .find((el) => {
        const click = el.getAttribute("@click") || "";
        const m = click.match(/clipboard\.writeText\((?:'([^']*)'|"([^"]*)")\)/);
        return m && (m[1] || m[2] || "").includes(",");
      });
    const tagsClick = tagsButton ? (tagsButton.getAttribute("@click") || "") : "";
    const tagsMatch = tagsClick.match(/clipboard\.writeText\((?:'([^']*)'|"([^"]*)")\)/);
    const tags = clean(tagsMatch ? (tagsMatch[1] || tagsMatch[2] || "") : "");
    const imageUrls = imageCandidates
      .map((candidate) => candidate.url)
      .filter((url, index, all) => url && all.indexOf(url) === index);
    const price = value(/(?:^|\s)([\d.,]+\s*USD)\s+(?:View on Etsy|Preview)/i);
    const sold = value(/Estimated Total Sales:\s*([\d,]+)\+?\s*Sold/i);
    const revenue = value(/Estimated Revenue:\s*([\d.,]+\s*[KM]?)\s*USD/i);
    const viewsAverage = value(/This is the estimated average daily view\.\s*([\d.,]+\s*[KM]?)\s*\(Avg\)/i);
    const views = value(/Total views of the listing\.\s*([\d.,]+\s*[KM]?)/i);
    const favoriteRate = value(/rate of favorites per 100 views\.\s*([\d.]+)\s*%/i);
    const favorites = value(/Total number of favorites for this listing\.\s*([\d.,]+\s*[KM]?)/i);
    const createdBlock = T.match(/The listing was created\.\s*(\d{1,2}\/\d{1,2}\/\d{4})(?:\s*\(([^)]+)\))?/i);
    const updatedBlock = T.match(/The listing was last updated\.\s*(\d{1,2}\/\d{1,2}\/\d{4})(?:\s*\(([^)]+)\))?/i);
    let ageDays = "";
    const ageText = createdBlock ? clean(createdBlock[2] || "") : "";
    const ageMatch = ageText.match(/(\d+)\s*(day|week|month|year)s?/i);
    if (ageMatch) {
      const factors = { day: 1, week: 7, month: 30, year: 365 };
      ageDays = String(parseInt(ageMatch[1], 10) * factors[ageMatch[2].toLowerCase()]);
    }
    const conversion = value(/Estimated conversion rate of the listing\.\s*~?\s*(-?[\d.]+)\s*%/i);
    const shopSales = value(/([\d,]+)\s+Sales\s+Chart on HeyEtsy\.com/i);
    const shopRating = value(/([\d.]+)\s+out of 5 stars/i);
    const shopReviews = value(/([\d,]+)\s+reviews/i);
    const headers = [
      "listing_id", "title", "shop", "price", "estimated_sold",
      "estimated_revenue_usd", "views_average", "views", "favorite_rate_pct",
      "favorites", "created", "listing_age_days", "age_text", "updated", "updated_ago",
      "conversion_pct", "shop_sales", "shop_rating", "shop_reviews",
      "shop_url", "tags", "image_urls", "main_image", "etsy_url", "heyetsy_url",
      "evidence_source", "evidence_note"
    ];
    const row = [
      listingId, title, shop, price, sold, revenue, viewsAverage, views,
      favoriteRate, favorites,
      createdBlock ? createdBlock[1] : "", ageDays,
      ageText,
      updatedBlock ? updatedBlock[1] : "", updatedBlock ? clean(updatedBlock[2] || "") : "",
      conversion, shopSales, shopRating, shopReviews, shopUrl, tags,
      JSON.stringify(imageUrls), imageUrl, etsyLink.split("?")[0],
      location.href.split("?")[0], "heyetsy_third_party",
      "HeyEtsy values are estimates captured from the rendered page; empty values were not inferred."
    ];
    return { headers, rows: [row] };
  }

  // ---- Etsy listing reviews --------------------------------------------------
  // Reviews are a separate evidence type. They must never be merged into the
  // listing-sales row because review language and HeyEtsy estimates have
  // different provenance. Capture only review cards currently rendered by
  // Etsy, plus Etsy's rendered aggregate/tag summaries.
  function parseJsonAttr(el, name) {
    if (!el) return null;
    try { return JSON.parse(el.getAttribute(name) || ""); } catch (e) { return null; }
  }

  function reviewSummary() {
    const pageText = clean(document.body.innerText || document.body.textContent || "");
    const featureEl = document.querySelector('[data-appears-component-name="reviews_feature_tags"]');
    const categoryEl = document.querySelector('[data-appears-component-name="reviews_categorical_tags"]');
    const featureData = parseJsonAttr(featureEl, "data-appears-event-data") || {};
    const categoryData = parseJsonAttr(categoryEl, "data-appears-event-data") || {};
    const containerEl = document.querySelector('[data-appears-component-name="listing_page_reviews_container_top"]');
    const containerData = parseJsonAttr(containerEl, "data-appears-event-data") || {};
    const ratingMatch = pageText.match(/Reviews for this item\s*.*?([\d.]+)\s*Item average/i);
    const recommendMatch = pageText.match(/(\d{1,3})%\s*Buyers recommend/i);
    const subrating = (label) => {
      const re = new RegExp("([\\d.]+)\\s*" + label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i");
      const m = pageText.match(re);
      return m ? m[1] : "";
    };
    return {
      listing_rating: ratingMatch ? ratingMatch[1] : "",
      listing_review_count: String(containerData.listing_rating_count || ""),
      shop_review_count: String(containerData.shop_rating_count || ""),
      buyers_recommend_pct: recommendMatch ? recommendMatch[1] : "",
      item_quality_rating: subrating("Item quality"),
      shipping_rating: subrating("Shipping"),
      customer_service_rating: subrating("Customer service"),
      feature_tags_json: JSON.stringify(featureData.tags || []),
      categorical_tags_json: JSON.stringify(categoryData.tags || [])
    };
  }

  function extractEtsyReviews() {
    if (!isEtsyListing()) return null;
    const idMatch = location.pathname.match(/\/listing\/(\d+)/);
    const listingId = idMatch ? idMatch[1] : "";
    const listingUrl = location.origin + location.pathname.replace(/\/$/, "");
    const title = clean(document.querySelector("h1")?.textContent ||
      document.querySelector('meta[property="og:title"]')?.content || document.title);
    const shopLink = document.querySelector('a[href*="/shop/"]');
    const shopMatch = (shopLink?.href || "").match(/\/shop\/([^/?#]+)/);
    const shop = shopMatch ? decodeURIComponent(shopMatch[1]) : clean(shopLink?.textContent || "");
    const summary = reviewSummary();
    const headers = [
      "review_id", "listing_id", "listing_title", "shop", "rating",
      "review_date_raw", "review_text", "buyer_display_name",
      "variation_json", "review_image_id", "review_photo_url",
      "listing_rating", "listing_review_count", "shop_review_count",
      "buyers_recommend_pct", "item_quality_rating", "shipping_rating",
      "customer_service_rating", "feature_tags_json", "categorical_tags_json",
      "etsy_url", "evidence_source", "evidence_note"
    ];
    const rows = [];
    for (const card of document.querySelectorAll("[data-review-container]")) {
      const reviewId = card.getAttribute("data-content-pane") || "";
      const text = clean(card.querySelector("[data-review-text]")?.textContent || "");
      if (!reviewId && !text) continue;
      const rating = card.querySelector('input[name="rating"]')?.value ||
        card.querySelector('input[name="initial-rating"]')?.value || "";
      const buyerInfo = card.querySelector(".buyer-info");
      const buyer = clean(buyerInfo?.querySelector(".buyer-name")?.textContent || "");
      const dateEl = buyerInfo && Array.from(buyerInfo.children)
        .find((el) => !el.classList.contains("buyer-name"));
      const reviewDate = clean(dateEl?.textContent || "");
      const variations = {};
      for (const li of card.querySelectorAll(".variation-info")) {
        const key = clean(li.querySelector(".wt-text-caption-title")?.textContent || "")
          .replace(/:\s*$/, "");
        const values = Array.from(li.querySelectorAll(".wt-text-caption"))
          .map((el) => clean(el.textContent)).filter(Boolean);
        if (key && values.length) variations[key] = values.join(" ");
      }
      const photo = Array.from(card.querySelectorAll("img"))
        .find((img) => !img.closest(".buyer-info") && !img.closest("[data-listing-card]") &&
          /etsystatic\.com/i.test(img.currentSrc || img.src || ""));
      rows.push([
        reviewId, card.getAttribute("data-listing-id") || listingId, title, shop,
        rating, reviewDate, text, buyer, JSON.stringify(variations),
        card.getAttribute("data-image-id") || "",
        photo ? (photo.currentSrc || photo.src || "") : "",
        summary.listing_rating, summary.listing_review_count, summary.shop_review_count,
        summary.buyers_recommend_pct, summary.item_quality_rating,
        summary.shipping_rating, summary.customer_service_rating,
        summary.feature_tags_json, summary.categorical_tags_json,
        listingUrl, "etsy_rendered_review",
        "Public review evidence captured from the rendered Etsy listing page; no sentiment or keywords were invented."
      ]);
    }
    return rows.length ? { headers, rows } : null;
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
    if (isHeyEtsy()) return "heyetsy";
    if (isEtsy()) return "etsy";
    if (isAmazon()) return "amazon";
    if (isAlibaba()) return "alibaba";
    if (isAliExpress()) return "aliexpress";
    if (is1688()) return "supplier-1688";
    if (isYtuongMe()) return "ytuongme";
    return "ytrends";
  }

  function viewSlug() {
    const q = new URLSearchParams(location.search).get("q") ||
      new URLSearchParams(location.search).get("k") ||          // amazon uses k=
      new URLSearchParams(location.search).get("SearchText") || // alibaba/aliexpress
      new URLSearchParams(location.search).get("keywords") ||   // 1688
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
    else if (isHeyEtsyListing()) d = extractHeyEtsyListing();
    else if (isEtsy()) d = extractEtsy();
    else if (isAmazon()) d = extractAmazon();
    else if (isAlibaba() || isAliExpress() || is1688()) d = extractAlibaba();
    else {
      const table = pickTable();
      if (table) d = extractTable(table);
      // ytuong.me card pages (Hot / listing grids) have no table -> card extractor
      if ((!d || !d.rows.length) && isYtuongMe()) d = extractYtuongHot();
    }
    return d && d.rows.length ? d : null;
  }

  function payload(data, meta) {
    const m = meta || {};
    return {
      schema_version: "1.1",
      exporter_version: "3.4.0",
      view: m.view || `${sourceTag()}-${viewSlug()}`,
      captured_at: new Date().toISOString(),
      source: m.source || location.href,
      source_type: m.sourceType ||
        (isHeyEtsyListing() ? "heyetsy_listing_detail" : sourceTag()),
      evidence_policy: "rendered_page_only_no_invention",
      headers: data.headers,
      rows: data.rows
    };
  }

  function download(text, name, mime) {
    // BOM only for CSV (Excel needs it); NEVER for JSON (breaks strict parsers)
    const isJson = (mime || "").includes("json");
    const blob = new Blob([isJson ? text : "﻿" + text],
      { type: mime || "text/csv;charset=utf-8" });
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

  // Shared POST used by both single-page Send and batch Send. Works on EVERY
  // site: payload() tags the view by sourceTag()/viewSlug() of the current page,
  // and the agent auto-routes by columns. Always posts to /api/import only.
  function sendData(data, label, meta) {
    chrome.storage.local.get({ agentUrl: "", agentToken: "", operator: "" }, (cfg) => {
      const url = (cfg.agentUrl || "").trim();
      if (!url) { flash("Set your agent import URL in the extension popup first.", false); return; }
      flash("Sending " + label + " to agent...", null);
      const body = payload(data, meta);
      if ((cfg.operator || "").trim()) body.operator = cfg.operator.trim();
      agentPost(url, cfg.agentToken, body, (r) => {
        if (!r.ok) {
          flash("Send failed: " + responseError(r), false);
          return;
        }
        const d = r.data || {};
        const detail = d.type ? ` → ${d.type}` : "";
        flash(`Sent ${d.rows_received ?? data.rows.length} rows (${label})${detail} ✓`, true);
      });
    });
  }

  function onSend() {
    const data = currentData();
    if (!data) { flash("No data found on this page.", false); return; }
    sendData(data, sourceTag());
  }

  // Review rows use their own batch so listing/search evidence can never be
  // mixed with review text. Etsy may replace review cards when the user changes
  // review page or filter; each click captures the cards currently rendered.
  function loadReviewBatch(cb) {
    chrome.storage.local.get({ ytxReviewBatch: null }, (o) => cb(o.ytxReviewBatch));
  }
  function saveReviewBatch(b, cb) {
    chrome.storage.local.set({ ytxReviewBatch: b }, cb || (() => {}));
  }
  function updateReviewButtons(b) {
    const n = b?.rows?.length || 0;
    const csv = document.getElementById("ytx-reviews-csv");
    const send = document.getElementById("ytx-reviews-send");
    if (csv) csv.textContent = n ? `Reviews CSV (${n})` : "Reviews CSV";
    if (send) send.textContent = n ? `Send reviews (${n})` : "Send reviews";
  }
  function onAddReviews() {
    const data = extractEtsyReviews();
    if (!data) { flash("No rendered listing reviews found.", false); return; }
    const listingId = data.rows[0][data.headers.indexOf("listing_id")] || "";
    loadReviewBatch((b) => {
      if (b && b.listingId !== listingId && b.rows.length) {
        flash(`Review batch belongs to listing ${b.listingId}. Clear it before adding ${listingId}.`, false);
        return;
      }
      if (!b || b.listingId !== listingId) {
        b = {
          listingId, headers: data.headers, rows: [], pageKeys: [],
          source: location.href.split("#")[0]
        };
      }
      const idIndex = b.headers.indexOf("review_id");
      const seen = new Set(b.rows.map((row) => String(row[idIndex] || JSON.stringify(row))));
      let added = 0;
      for (const row of data.rows) {
        const key = String(row[idIndex] || JSON.stringify(row));
        if (seen.has(key)) continue;
        seen.add(key); b.rows.push(row); added++;
      }
      const pageKey = location.href.split("#")[0] + "|" +
        b.rows.map((row) => row[idIndex]).slice(-data.rows.length).join(",");
      if (!b.pageKeys.includes(pageKey)) b.pageKeys.push(pageKey);
      saveReviewBatch(b, () => {
        updateReviewButtons(b);
        flash(`Review batch: ${b.rows.length} unique reviews (+${added} new).`, true);
      });
    });
  }
  function onReviewsCSV() {
    loadReviewBatch((b) => {
      if (!b?.rows?.length) {
        const data = extractEtsyReviews();
        if (!data) { flash("No review batch or rendered reviews found.", false); return; }
        download(toCSV(data), `etsy_reviews_${data.rows[0][1]}_${today()}.csv`);
        flash(`Downloaded ${data.rows.length} rendered reviews.`, true);
        return;
      }
      download(toCSV(b), `etsy_reviews_${b.listingId}_${b.rows.length}_${today()}.csv`);
      flash(`Downloaded ${b.rows.length} unique reviews.`, true);
    });
  }
  function onReviewsSend() {
    loadReviewBatch((b) => {
      const data = b?.rows?.length ? { headers: b.headers, rows: b.rows } : extractEtsyReviews();
      if (!data) { flash("No review batch or rendered reviews found.", false); return; }
      const listingId = data.rows[0][data.headers.indexOf("listing_id")] || "";
      sendData(data, `Etsy reviews ${listingId}`, {
        source: b?.source || location.href,
        sourceType: "etsy_listing_reviews",
        view: `etsy-listing-${listingId}-reviews`
      });
    });
  }
  function onReviewsClear() {
    chrome.storage.local.remove("ytxReviewBatch", () => {
      updateReviewButtons(null);
      flash("Review batch cleared.", true);
    });
  }

  // ---- multi-page batch: accumulate pages you visit into ONE de-duped set ----
  // Survives page navigation via chrome.storage.local, so on paginated sites
  // (Etsy, Amazon) you click "+ Add page" on page 1, go to page 2, add again...
  // then export or send the whole thing as one CSV. Read-only: YOU click Next.
  function batchKeyCol(headers) {
    const ids = ["listing_id", "asin", "pin_id", "offer_id"];
    for (const n of ids) { const i = headers.indexOf(n); if (i >= 0) return i; }
    for (let i = 0; i < headers.length; i++) if (/url$/i.test(headers[i])) return i;
    return -1; // fall back to whole-row signature
  }
  function rowKey(b, r) {
    const key = b.keyCol >= 0 ? String(r[b.keyCol] || "").trim() : "";
    return key || JSON.stringify(r);
  }
  function loadBatch(cb) { chrome.storage.local.get({ ytxBatch: null }, (o) => cb(o.ytxBatch)); }
  function saveBatch(b, cb) { chrome.storage.local.set({ ytxBatch: b }, cb || (() => {})); }

  function updateBatchBtn(b) {
    const el = document.getElementById("ytx-batch-csv");
    if (el) el.textContent = (b && b.rows.length) ? `Batch CSV (${b.rows.length})` : "Batch CSV";
    const sd = document.getElementById("ytx-batch-send");
    if (sd) sd.textContent = (b && b.rows.length) ? `Send batch (${b.rows.length})` : "Send batch";
  }

  async function onAddPage() {
    const btn = document.getElementById("ytx-add");
    if (btn) btn.disabled = true;
    flash("Loading full page to add to batch...", null);
    try {
      await grabAll((n, done) => flash((done ? "Loaded " : "Loading ") + n + " rows...", null));
      const data = currentData();
      if (!data) { flash("No data found to add.", false); return; }
      const site = sourceTag();
      const sig = site + "|" + data.headers.join(",");
      loadBatch((b) => {
        if (b && b.sig !== sig && b.rows.length) {
          flash(`Batch holds ${b.site} data (${b.rows.length} rows). Click Clear to `
                + `start a new ${site} batch.`, false);
          return;
        }
        if (!b || b.sig !== sig) {
          b = {
            sig, site, headers: data.headers, rows: [], pages: 0,
            keyCol: batchKeyCol(data.headers), pageKeys: [],
            source: location.href,
            sourceType: isHeyEtsyListing() ? "heyetsy_listing_detail" : site,
            view: `${site}-${viewSlug()}`
          };
        }
        const seen = new Set(b.rows.map((r) => rowKey(b, r)));
        let added = 0;
        for (const r of data.rows) {
          const k = rowKey(b, r);
          if (seen.has(k)) continue;
          seen.add(k); b.rows.push(r); added++;
        }
        if (!Array.isArray(b.pageKeys)) b.pageKeys = [];
        const pageKey = location.href.split("#")[0];
        if (!b.pageKeys.includes(pageKey)) {
          b.pageKeys.push(pageKey);
          b.pages = b.pageKeys.length;
        }
        saveBatch(b, () => {
          updateBatchBtn(b);
          flash(`Batch: ${b.rows.length} rows over ${b.pages} page(s)  (+${added} new).`, true);
        });
      });
    } catch (e) {
      flash("Add page failed: " + e.message, false);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function onBatchCSV() {
    loadBatch((b) => {
      if (!b || !b.rows.length) { flash("Batch is empty - click '+ Add page' first.", false); return; }
      download(toCSV({ headers: b.headers, rows: b.rows }),
               `${b.site}_batch_${b.pages}pages_${today()}.csv`);
      flash(`Downloaded batch: ${b.rows.length} rows over ${b.pages} page(s).`, true);
    });
  }

  function onBatchSend() {
    loadBatch((b) => {
      if (!b || !b.rows.length) { flash("Batch is empty - click '+ Add page' first.", false); return; }
      sendData(
        { headers: b.headers, rows: b.rows },
        `${b.site} batch / ${b.pages} pages`,
        { source: b.source, sourceType: b.sourceType, view: b.view }
      );
    });
  }

  function onBatchClear() {
    saveBatch(null, () => { updateBatchBtn(null); flash("Batch cleared.", true); });
  }

  // ---- auto-scroll: load lazy / infinite-scroll rows before capture ----------
  function rowCount() { const d = currentData(); return d ? d.rows.length : 0; }
  function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

  // Scroll to the bottom repeatedly so lazy-loaded / infinite-scroll rows
  // render, until the detected row count stops growing (or we hit a safety
  // limit). READ-ONLY: we only scroll the window - we never click "Next", never
  // automate a marketplace, never log in. Same data "Save Page As" would keep,
  // we just make the page finish loading first.
  async function grabAll(onProgress) {
    const MAX_STEPS = 600;     // hard cap on scroll iterations
    const MAX_MS = 240000;     // ... and on total time (4 min)
    const STABLE_NEEDED = 5;   // stop after N passes with no new rows
    const start = Date.now();
    let last = rowCount();
    let stable = 0;
    if (onProgress) onProgress(last, false);
    for (let i = 0; i < MAX_STEPS; i++) {
      if (Date.now() - start > MAX_MS) break;
      window.scrollTo(0, document.documentElement.scrollHeight);
      await sleep(150);
      window.scrollBy(0, -250);   // nudge: some grids only fire on a fresh delta
      await sleep(700);
      const now = rowCount();
      if (onProgress) onProgress(now, false);
      if (now > last) { last = now; stable = 0; }
      else if (++stable >= STABLE_NEEDED) break;
    }
    window.scrollTo(0, 0);
    if (onProgress) onProgress(last, true);
    return last;
  }

  async function onGrabAll() {
    const btn = document.getElementById("ytx-grab");
    if (btn) btn.disabled = true;
    flash("Grabbing all - scrolling to load everything...", null);
    try {
      await grabAll((n, done) =>
        flash((done ? "Loaded " : "Loading ") + n + " rows" +
              (done ? " - exporting..." : "..."), done ? true : null));
      const data = currentData();
      if (!data) { flash("No data found after scrolling.", false); return; }
      download(toCSV(data), `${sourceTag()}_${viewSlug()}_${today()}_all.csv`);
      flash(`Grabbed ${data.rows.length} rows (${sourceTag()}) - CSV saved.`, true);
    } catch (e) {
      flash("Grab all failed: " + e.message, false);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  // ---- UI --------------------------------------------------------------------
  function buildToolbar() {
    if (document.getElementById(BTN_ID)) return;
    const bar = document.createElement("div");
    bar.id = BTN_ID;
    bar.innerHTML =
      '<div class="ytx-row">' +
      '  <span class="ytx-brand">' + sourceTag().toUpperCase() + ' &rarr; Evidence Exporter</span>' +
      '  <button id="ytx-grab" class="ytx-btn ytx-primary" title="Auto-scroll to load every row on this page, then download CSV">&darr; Grab all</button>' +
      '  <button id="ytx-export" class="ytx-btn">CSV now</button>' +
      '  <button id="ytx-json" class="ytx-btn">JSON</button>' +
      '  <button id="ytx-send" class="ytx-btn">Send to agent</button>' +
      '  <button id="ytx-hide" class="ytx-x" title="Hide">&times;</button>' +
      '</div>' +
      '<div class="ytx-row ytx-row2">' +
      '  <span class="ytx-tag" title="Combine several pages into one CSV - great for Etsy/Amazon paging">Multi-page</span>' +
      '  <button id="ytx-add" class="ytx-btn ytx-sm" title="Load this whole page and add its rows to the running batch (de-duped)">+ Add page</button>' +
      '  <button id="ytx-batch-csv" class="ytx-btn ytx-sm">Batch CSV</button>' +
      '  <button id="ytx-batch-send" class="ytx-btn ytx-sm">Send batch</button>' +
      '  <button id="ytx-batch-clear" class="ytx-btn ytx-sm" title="Empty the batch">Clear</button>' +
      '</div>' +
      (isEtsyListing() ?
      '<div class="ytx-row ytx-row2">' +
      '  <span class="ytx-tag" title="Capture only public reviews currently rendered by Etsy">Listing reviews</span>' +
      '  <button id="ytx-reviews-add" class="ytx-btn ytx-sm" title="Add currently rendered reviews to a separate de-duplicated batch">+ Add reviews</button>' +
      '  <button id="ytx-reviews-csv" class="ytx-btn ytx-sm">Reviews CSV</button>' +
      '  <button id="ytx-reviews-send" class="ytx-btn ytx-sm">Send reviews</button>' +
      '  <button id="ytx-reviews-clear" class="ytx-btn ytx-sm">Clear reviews</button>' +
      '</div>' : '') +
      '<div id="ytx-status" class="ytx-status"></div>';
    document.body.appendChild(bar);
    document.getElementById("ytx-grab").addEventListener("click", onGrabAll);
    document.getElementById("ytx-export").addEventListener("click", onExport);
    document.getElementById("ytx-json").addEventListener("click", onJson);
    document.getElementById("ytx-send").addEventListener("click", onSend);
    document.getElementById("ytx-add").addEventListener("click", onAddPage);
    document.getElementById("ytx-batch-csv").addEventListener("click", onBatchCSV);
    document.getElementById("ytx-batch-send").addEventListener("click", onBatchSend);
    document.getElementById("ytx-batch-clear").addEventListener("click", onBatchClear);
    if (isEtsyListing()) {
      document.getElementById("ytx-reviews-add").addEventListener("click", onAddReviews);
      document.getElementById("ytx-reviews-csv").addEventListener("click", onReviewsCSV);
      document.getElementById("ytx-reviews-send").addEventListener("click", onReviewsSend);
      document.getElementById("ytx-reviews-clear").addEventListener("click", onReviewsClear);
      loadReviewBatch(updateReviewButtons);
    }
    document.getElementById("ytx-hide").addEventListener("click", () => bar.remove());
    loadBatch(updateBatchBtn);   // restore the running batch count across pages
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
