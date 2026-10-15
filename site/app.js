/* 山姆商品查询 H5：加载数据，按地址 # 后面的部分渲染首页、分类、搜索、详情四种页面。纯函数在 lib.js（window.SamsLib）。
   站内跳转都用 history.pushState / replaceState，自己渲染；浏览器返回键触发 hashchange 再渲染。
   每条历史记录带 {d: 站内第几层}：d>0 时左上角返回用 history.back()；从分享链接直接打开（d=0）时回首页，不会退出网站。 */
(function () {
  "use strict";
  const L = window.SamsLib;
  const app = document.getElementById("app");
  const scrolls = {};                     // 每个地址离开时的滚动位置，返回时恢复
  const byId = {}, bySub = {};
  let data = null, topCounts = [], current = null, lastDepth = 0, timer = null;

  function depth() { return (history.state && history.state.d) || 0; }

  function go(href, replace) {
    if (replace) history.replaceState({ d: depth() }, "", href);
    else history.pushState({ d: depth() + 1 }, "", href);
    render();
  }

  function goBack(fallback) {
    if (depth() > 0) history.back();
    else go(fallback, true);
  }

  function bar(inner) { return `<div class="bar">${inner}</div>`; }
  function backLink(href) { return `<a class="back" href="${href}" data-back aria-label="返回">‹</a>`; }
  function note() { return `<div class="note">价格为 ${L.esc(data.meta.app_date)} 山姆 App 快照，仅供参考</div>`; }
  function stateTags(it) {
    return (it.x ? '<span class="tag fast">极速达</span>' : "") + (it.o ? '<span class="tag oos">无货</span>' : "");
  }

  function row(it) {
    return `<a class="row${it.o ? " oos" : ""}" href="#/p/${encodeURIComponent(it.id)}">
      <img loading="lazy" alt="" src="${L.esc(L.imgSrc(it, false))}" onerror="this.onerror=null;this.src=SamsLib.PLACEHOLDER">
      <div class="info"><div class="name">${L.esc(it.n)}</div><div class="spec">${L.esc(it.s)}</div>
      <div class="price">${L.formatPrice(it.p)}</div><div class="tags">${stateTags(it)}</div></div></a>`;
  }

  // 首页和搜索结果共用顶部搜索框；边输边搜时只换下面的内容，输入框不重建，手机键盘不会收起
  function homeOrSearch(r) {
    const q = r.page === "search" ? r.q : "";
    let input = app.querySelector(".search input");
    if (!input) {
      app.innerHTML = bar('<form class="search" action="#"><input type="search" placeholder="搜索商品名、品牌或规格" ' +
        'enterkeyhint="search" autocomplete="off"></form>') + '<div id="main"></div>';
      input = app.querySelector(".search input");
      bindSearch(input);
    }
    if (document.activeElement !== input) input.value = q;
    const main = document.getElementById("main");
    if (!L.tokens(q).length) {
      const grid = data.cats.map((c, ti) =>
        `<a href="#/c/${ti}/0">${L.esc(c.name)}<small>${topCounts[ti]}</small></a>`).join("");
      main.innerHTML = note() + `<div class="grid">${grid}</div>`;
      return;
    }
    const { results, total } = L.search(data.items, q), msg = L.searchMessage(q, total);
    main.innerHTML = (msg ? `<p class="msg">${L.esc(msg)}</p>` : "") + results.map(row).join("");
  }

  function bindSearch(input) {
    input.form.addEventListener("submit", e => { e.preventDefault(); input.blur(); });
    input.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        const href = L.searchHref(input.value), onSearch = L.parseRoute(location.hash).page === "search";
        if (href === (location.hash || "#/")) return;
        if (href === "#/" && onSearch && depth() > 0) history.back();   // 清空了搜索词：回到来时的首页
        else go(href, onSearch);                                          // 从首页开始搜记一条历史，之后的输入只替换它
      }, 250);
    });
  }

  function category(r) {
    const top = data.cats[r.top];
    if (!top) { go("#/", true); return; }
    const si = r.sub < top.subs.length ? r.sub : 0;
    const old = app.querySelector(".side");
    const sideTop = old && old.dataset.top === String(r.top) ? old.scrollTop : 0;   // 同一大类里换子分类，左栏不跳回顶部
    const side = top.subs.map((s, i) => `<a class="${i === si ? "on" : ""}" href="#/c/${r.top}/${i}" data-replace>` +
      `${L.esc(s.name)}<small>${s.n}</small></a>`).join("");
    const list = (bySub[r.top + "," + si] || []).map(row).join("");
    app.innerHTML = bar(backLink("#/") + `<span class="title">${L.esc(top.name)}</span>`) +
      `<div class="cat"><nav class="side" data-top="${r.top}">${side}</nav>` +
      `<div class="list">${list || '<p class="msg">这个分类没有商品</p>'}</div></div>`;
    app.querySelector(".side").scrollTop = sideTop;
  }

  function item(r) {
    const it = byId[r.id];
    if (!it) {
      app.innerHTML = bar(backLink("#/") + '<span class="title">商品不存在</span>') +
        '<p class="msg">没有这个商品，可能数据已更新。<a href="#/" data-replace>回首页</a></p>';
      return;
    }
    const tags = stateTags(it) + it.t.map(t => `<span class="tag">${L.esc(t)}</span>`).join("");
    const cats = it.c.filter(([t, s]) => data.cats[t] && data.cats[t].subs[s]).map(([t, s]) =>
      `<a href="#/c/${t}/${s}">${L.esc(data.cats[t].name)} / ${L.esc(data.cats[t].subs[s].name)}</a>`).join("");
    app.innerHTML = bar(backLink("#/") + `<span class="title">${L.esc(it.n)}</span>`) +
      `<div class="detail"><img alt="" src="${L.esc(L.imgSrc(it, true))}" onerror="this.onerror=null;this.src=SamsLib.PLACEHOLDER">
      <div class="body"><h1>${L.esc(it.n)}</h1><div class="spec">${L.esc(it.s)}</div>
      <div class="price">${L.formatPrice(it.p)}</div><div class="tags">${tags}</div>
      ${it.d ? `<p class="desc">${L.esc(it.d)}</p>` : ""}
      <div class="cats">所在分类：${cats}</div></div></div>` + note();
  }

  function render() {
    if (current !== null) scrolls[current] = window.scrollY;
    current = location.hash || "#/";
    lastDepth = depth();
    const r = L.parseRoute(location.hash);
    if (r.page === "cat") category(r);
    else if (r.page === "item") item(r);
    else homeOrSearch(r);
    window.scrollTo(0, scrolls[current] || 0);
  }

  app.addEventListener("click", e => {
    const a = e.target.closest("a[href^='#']");
    if (!a || !data) return;
    e.preventDefault();
    const href = a.getAttribute("href");
    if (a.hasAttribute("data-back")) goBack(href);
    else if (href !== (location.hash || "#/")) go(href, a.hasAttribute("data-replace"));
  });

  window.addEventListener("hashchange", () => {
    if (!data) return;
    if (!history.state) history.replaceState({ d: lastDepth + 1 }, "");   // 手动改了地址：当成往前走了一步
    render();
  });

  if ("scrollRestoration" in history) history.scrollRestoration = "manual";
  if (!history.state) history.replaceState({ d: 0 }, "");

  fetch(document.body.dataset.src)
    .then(res => { if (!res.ok) throw new Error(res.status); return res.json(); })
    .then(d => {
      data = d;
      topCounts = d.cats.map(() => 0);
      d.items.forEach(it => {
        byId[it.id] = it;
        it.c.forEach(([t, s]) => { (bySub[t + "," + s] = bySub[t + "," + s] || []).push(it); });
        new Set(it.c.map(c => c[0])).forEach(t => { topCounts[t]++; });
      });
      render();
    })
    .catch(() => { app.innerHTML = '<p class="msg">商品数据加载失败，请刷新重试</p>'; });
})();
