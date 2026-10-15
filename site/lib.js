/* 山姆商品查询 H5 的纯函数：搜索、路由、格式化。浏览器里是 window.SamsLib，Node 里 require 得到同一组函数。 */
(function (root) {
  "use strict";
  const LIMIT = 200;
  const PLACEHOLDER = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="#f2f3f5"/>' +
    '<text x="50" y="56" font-size="14" text-anchor="middle" fill="#b0b4ba">暂无图片</text></svg>');

  // 比较前统一：全角转半角（NFKC）、各种撇号统一成 '、转小写、连续空白并成一个
  function normalize(s) {
    return String(s == null ? "" : s).normalize("NFKC").replace(/[’‘`´]/g, "'")
      .toLowerCase().replace(/\s+/g, " ").trim();
  }

  function tokens(q) {
    const n = normalize(q);
    return n ? n.split(" ") : [];
  }

  // 每个词都要出现在商品名、规格或卖点里。最多返回 limit 条，total 是全部命中数
  function search(items, q, limit) {
    const max = limit || LIMIT, toks = tokens(q);
    if (!toks.length) return { results: [], total: 0 };
    const results = [];
    let total = 0;
    for (const it of items) {
      if (it._h === undefined) it._h = normalize([it.n, it.s, it.d].join(" "));
      if (toks.every(t => it._h.includes(t))) {
        total++;
        if (results.length < max) results.push(it);
      }
    }
    return { results, total };
  }

  // 搜索结果上方的提示；不需要提示时返回空串。空查询由页面显示首页的大类，不走这里
  function searchMessage(q, total) {
    if (total === 0) return `没有找到「${String(q).trim()}」`;
    if (total > LIMIT) return `结果太多，请再加一个词（共 ${total} 个）`;
    return "";
  }

  function searchHref(q) {
    return tokens(q).length ? "#/s/" + encodeURIComponent(String(q).trim()) : "#/";
  }

  function decode(s) {
    try { return decodeURIComponent(s); } catch (e) { return s; }
  }

  function parseRoute(hash) {
    const parts = String(hash || "").replace(/^#\/?/, "").split("/");
    const num = s => (/^\d+$/.test(s || "") ? Number(s) : null);
    if (parts[0] === "c" && num(parts[1]) !== null) return { page: "cat", top: num(parts[1]), sub: num(parts[2]) || 0 };
    if (parts[0] === "p" && parts[1]) return { page: "item", id: decode(parts[1]) };
    if (parts[0] === "s") return { page: "search", q: decode(parts.slice(1).join("/")) };
    return { page: "home" };
  }

  function formatPrice(p) {
    const [int, dec] = String(Math.round(p * 100) / 100).split(".");
    return "¥" + int.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + (dec ? "." + dec : "");
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g,
      c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  }

  function imgSrc(item, large) {
    return (large ? item.il || item.it : item.it) || PLACEHOLDER;
  }

  const api = { LIMIT, PLACEHOLDER, normalize, tokens, search, searchMessage, searchHref, parseRoute,
                formatPrice, esc, imgSrc };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SamsLib = api;
})(typeof self !== "undefined" ? self : this);
