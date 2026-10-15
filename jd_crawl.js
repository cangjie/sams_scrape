// 在 mall.jd.com 的任意页面里执行：按店内二级分类逐页读商品列表，进度存 localStorage（__jd_rows / __jd_done / __jd_totals）。
// 分类树第一次从店铺首页的导航里读出来存到 __jd_cats，之后在 mall.jd.com 的任何页面都能续抓。
// 源码也存在 localStorage.__jd_src 里：续抓只要在页面里执行 eval(localStorage.__jd_src)。
//
// 这个脚本只抓列表（商品名、编号、图片、评价数、加密编号 enc），不取价格；价格由 jd_price.js 另外慢慢取。原因见下。
//
// 京东有两道互相独立的限速，超了都返回 403，而且越撞越严、按天重置（零点后恢复）：
// 1. 列表接口（api.m.jd.com 的 moduleHtmlColor）。2026-10-11 早上第一轮 8.6 秒一页，连续 8 页后被挡，2 分多钟就恢复；
//    之后每隔 1～5 分钟重试只会一直 403，并被收紧成「放行 1 页就要静默 10 分钟」，傍晚又收紧到 15～25 分钟、时灵时不灵，
//    中间完全停手 3.6 小时也不恢复。10-12 零点一过，1 分钟的间隔就又放行了。
//    计数的是「访问分类页」本身（单独 fetch 一次分类页 HTML 也算一次），地址里的每页条数改大不被接受（只给 24 个）。
// 2. 价格接口（mGetsByColor，一次最多 10 个商品）。页面脚本只给「视口内」的商品取价——以前把 iframe 拉到几万像素高，
//    等于每页一口气发 2～3 次取价请求，10-12 凌晨连着十来页之后价格接口开始 403；再在页面里手动重取，
//    京东直接把那个 iframe 跳去了别的域名（多半是验证页）。所以现在 iframe 只有 40 像素高：商品都在视口外，页面一次价格都不取。
//
// 节奏：平时用 P.gap（被挡就停、把间隔拉长；连续 18 页没事才往下试一次）。零点后自动试一次 1 分钟间隔，
// 通过就进「快速档」（2 分半一页），快速档一被挡就退回原来的慢速间隔。
// 分类页上有两个异步模块各发一次 moduleHtmlColor：304231119 是商品列表，另一个用不着，赶在页面脚本发请求之前把它的占位删掉。
// 开始前想先静默一段时间：执行前设 window.__jdStartDelay = 毫秒数；等待中想提前/推后：改 __jd2.waitingUntil。
(() => {
  for (const k of ['__jd', '__jd2']) if (window[k] && !window[k].done) window[k].stopped = window[k].stopped || '被新的一轮替换';
  const load = k => { try { return JSON.parse(localStorage.getItem(k) || 'null'); } catch (e) { return null; } };
  let cats = []; let top = null; const seen = new Set();
  document.querySelectorAll('a[href*="view_search-633676-"]').forEach(a => {
    const m = a.href.match(/view_search-633676-(\d+)-/); if (!m) return;
    const name = (a.innerText || '').replace(/>/g, '').trim();
    if (a.closest('dt')) { top = {id: m[1], name}; if (!seen.has('t' + m[1])) { seen.add('t' + m[1]); cats.push({id: m[1], top: name, sub: '', level: 1}); } }
    else if (a.closest('dd') && top && !seen.has(m[1])) { seen.add(m[1]); cats.push({id: m[1], top: top.name, sub: name, level: 2}); }
  });
  if (cats.some(c => c.level === 2)) localStorage.setItem('__jd_cats', JSON.stringify(cats)); else cats = load('__jd_cats') || [];
  const leaves = cats.filter(c => c.level === 2);
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const hhmmss = () => new Date().toTimeString().slice(0, 8);
  const pace = load('__jd_pace') || {};
  const P = window.__jd2 = {cats, rows: load('__jd_rows') || [], doneKeys: load('__jd_done') || [], totals: load('__jd_totals') || {}, log: [], hist: load('__jd_hist') || [],
                            done: false, stopped: null, cur: '', pages: 0, blocked: 0, waitingUntil: 0, started: Date.now(),
                            gap: pace.gap || 300000, floor: pace.floor || 45000, clean: 0, fast: !!pace.fast, slow: pace.slow || null, probing: false};
  const save = () => { try {
    localStorage.setItem('__jd_rows', JSON.stringify(P.rows)); localStorage.setItem('__jd_done', JSON.stringify(P.doneKeys)); localStorage.setItem('__jd_totals', JSON.stringify(P.totals));
    localStorage.setItem('__jd_hist', JSON.stringify(P.hist)); localStorage.setItem('__jd_pace', JSON.stringify({gap: P.gap, floor: P.floor, fast: P.fast, slow: P.slow}));
  } catch (e) { P.saveErr = String(e); } };
  const nap = async ms => { P.waitingUntil = Date.now() + ms; while (!P.stopped && Date.now() < P.waitingUntil) await sleep(Math.min(1000, P.waitingUntil - Date.now())); P.waitingUntil = 0; };
  const LIST_MOD = '304231119';
  const SIZE = 24;
  const trim = d => d.querySelectorAll('.m_render_structure').forEach(e => { if (e.getAttribute('m_render_instance_id') !== LIST_MOD) e.remove(); });
  async function loadPage(cid, page) {
    const f = document.createElement('iframe');
    f.style.cssText = 'position:absolute;left:-9999px;top:0;width:1200px;height:40px;border:0';      // 矮：商品都在视口外，页面不取价格
    f.src = `https://mall.jd.com/view_search-633676-${cid}-1-1-${SIZE}-${page}.html`;
    document.body.appendChild(f);
    let mo = null, watched = null;
    const hook = setInterval(() => {
      let d = null; try { d = f.contentDocument; } catch (e) { clearInterval(hook); return; }
      if (P.noTrim || !d || d === watched || d.URL === 'about:blank') return;
      watched = d; trim(d);
      mo = new MutationObserver(() => trim(d)); mo.observe(d, {childList: true, subtree: true});
    }, 2);
    await new Promise(res => { f.onload = res; setTimeout(res, 15000); });
    clearInterval(hook); if (mo) mo.disconnect();
    let lis = [], total = null, d = null, api = [], priceCalls = 0;
    const deadline = Date.now() + 25000;
    while (Date.now() < deadline) {
      await sleep(500);
      try { d = f.contentDocument; } catch (e) { d = null; break; }
      if (!d || !d.body) continue;
      lis = Array.from(d.querySelectorAll('li')).filter(li => li.querySelector('a[href*="item.jd.com"]') && !li.querySelector('.jNum'));
      const m = d.body.innerText.match(/共(\d+)条记录/); total = m ? +m[1] : total;
      try { const es = f.contentWindow.performance.getEntriesByType('resource'); api = es.filter(e => /moduleHtmlColor/.test(e.name)).map(e => e.responseStatus || 0); priceCalls = es.filter(e => /mGetsByColor/.test(e.name)).length; } catch (e) {}
      if (total === null && api.length && api.every(s => s >= 400)) break;      // 列表接口已经明确被拒，不用等满
      if (total !== null && lis.length >= Math.min(total - (page - 1) * SIZE, SIZE)) break;          // 这一页的商品都出来了
    }
    let href = ''; try { href = f.contentWindow.location.href; } catch (e) { href = 'cross-origin'; }
    const rows = lis.map(li => {
      const a = li.querySelector('.jDesc a') || li.querySelector('a[href*="item.jd.com"]');
      const img = li.querySelector('.jPic img');
      const src = img ? (img.getAttribute('original') || img.src || '') : '';
      const enc = li.querySelector('[data-sku-encrypt]');
      return {sku: (a.href.match(/item\.jd\.com\/(\d+)\.html/) || [])[1], name: (a.innerText || '').trim(),
              sam: ((li.querySelector('[jspprice]') || {}).innerText || '').trim(),
              img: (src.match(/\/(jfs\/.+)$/) || [])[1] || src, ev: ((li.querySelector('.jEvaluate') || {}).innerText || '').trim(),
              enc: enc ? enc.getAttribute('data-sku-encrypt') : ''};
    });
    const title = d ? d.title.trim() : '';
    f.remove();
    return {rows, total, href, title, api, priceCalls};
  }
  P.run = (async () => {
    if (!leaves.length) { P.stopped = '没有分类树：先到店铺首页执行一次'; return; }
    if (window.__jdStartDelay) { const d = window.__jdStartDelay; window.__jdStartDelay = 0; await nap(d); }
    for (const c of leaves) {
      let page = 1, pages = Math.max(1, Math.ceil((P.totals[c.id] || 0) / SIZE));
      while (page <= pages) {
        const key = c.id + ':' + page;
        if (P.doneKeys.includes(key)) { page++; continue; }
        if (P.stopped) return;
        P.cur = `${c.top}/${c.sub} p${page}`;
        let r = null, cool = Math.max(600000, P.gap), soft = 0;
        for (let attempt = 0; attempt < 12; attempt++) {
          r = await loadPage(c.id, page);
          const ok = /view_search/.test(r.href) && r.total !== null;
          P.hist.push([hhmmss(), P.cur, ok ? 'ok' : 'blocked', r.api.join(','), Math.round(P.gap / 1000)]); if (P.hist.length > 200) P.hist.shift();
          if (ok) break;
          if (r.total === null && r.api.length && r.api.every(s => s === 200)) P.noTrim = true;   // 接口通了却没出列表：可能是删占位弄坏了页面，之后不删
          // 页面压根没打开（网络抖动：iframe 还停在 about:blank，或者成了浏览器的出错页——读不到地址，表现为 cross-origin）：
          // 先每分钟重试 5 次，还不行就每 10 分钟试一次（最多约 12 小时），网络恢复后自己接着抓，不算被挡。
          if (/^(about:blank|cross-origin)?$/.test(r.href) && ++soft <= 80) { save(); await nap(soft <= 5 ? 60000 : 600000); if (P.stopped) return; attempt--; continue; }
          if (!/view_search/.test(r.href)) { P.stopped = `被带到别的页面（可能要登录或人工验证）：${P.cur} → ${r.href.slice(0, 100)} | ${r.title.slice(0, 30)}`; save(); return; }
          P.blocked++;
          if (attempt === 0) {
            if (P.probing) { P.probing = false; P.fastNote = hhmmss() + ' 试探被挡，维持慢速'; }
            else if (P.fast) { P.fast = false; P.gap = (P.slow || {}).gap || 1248000; P.floor = (P.slow || {}).floor || 1104000; P.fastNote = hhmmss() + ' 快速档被挡，退回慢速'; }
            else { P.floor = Math.min(1800000, Math.round(P.gap * 1.15)); P.gap = Math.min(1800000, Math.round(P.gap * 1.3)); }
            P.clean = 0;
          }
          save();
          await nap(cool + Math.random() * 20000);
          cool = Math.max(900000, Math.round(P.gap * 1.2));
          if (P.stopped) return;
        }
        if (r.total === null) { P.stopped = `连续 12 次被限速：${P.cur} | api=${r.api.join(',')}`; save(); return; }
        P.totals[c.id] = r.total;
        pages = Math.max(1, Math.ceil(r.total / SIZE));
        r.rows.forEach(x => P.rows.push(Object.assign(x, {top: c.top, sub: c.sub, cid: c.id})));
        P.log.push([c.top, c.sub, page, r.total, r.rows.length, r.rows.filter(x => !x.enc).length, r.priceCalls]);   // 末两项：没拿到加密编号的行数、页面发出的取价请求数（应为 0）
        P.doneKeys.push(key);
        P.pages++; P.clean++;
        if (!P.fast && P.clean % 18 === 0) P.floor = Math.max(45000, Math.round(P.floor * 0.7));
        if (P.clean >= 2) P.gap = Math.max(P.floor, Math.round(P.gap * 0.85));   // 停完后的第一页验证的是停的时长，不是间隔
        save();
        page++;
        // 额度按天算：过了零点试一次 1 分钟的间隔，通过就进「快速档」（2 分半一页），快速档一被挡就退回原来的慢速间隔。每天只试一次。
        if (P.probing) { P.probing = false; P.fast = true; P.slow = {gap: P.gap, floor: P.floor}; P.gap = P.floor = 150000; P.fastNote = hhmmss() + ' 试探通过，进入快速档'; save(); }
        const day = new Date().toDateString();
        if (!P.fast && new Date().getHours() < 6 && localStorage.getItem('__jd_probe_day') !== day) { localStorage.setItem('__jd_probe_day', day); window.__jdNextGap = 60000; P.probing = true; }
        const g = window.__jdNextGap || P.gap; window.__jdNextGap = 0;        // 临时指定下一次间隔（试探用）
        await nap(g + Math.random() * 8000);
      }
    }
    P.done = true;
  })().catch(e => { P.stopped = 'JS 错误：' + e; });
  return {leaves: leaves.length, resumedRows: P.rows.length, doneKeys: P.doneKeys.length, gap: P.gap, floor: P.floor, fast: P.fast};
})()
