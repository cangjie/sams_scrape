// 给 jd_crawl.js 抓到的商品补「山姆会员价」。在 mall.jd.com 的任意页面（顶层标签页）里执行；续跑：eval(localStorage.__jdp_src)。
//
// 做法：打开一个分类页（隐藏 iframe，40 像素高：商品都在视口外，页面自己一个价也不取），列表出来后摘掉所有价格节点的
// jshop="price" 标记，每批只给 ≤10 个缺价商品的节点补上标记，调一次页面自己的 JD_local_price(容器)（price.p.js 里的，不看视口，
// 容器里带标记的都取；请求由页面脚本自己签名、发出），等价格填进节点后读出来。一次取价请求（mGetsByColor）最多 10 个商品。
//
// 2026-10-12～13 实测：
// - 只能取这一页上现成的节点。取价请求带的是节点上的加密编号（data-sku-encrypt，64 位十六进制），每次打开页面都不一样
//   （同一页上所有商品的开头一段相同，换一次页面就变），存下来的旧编号拿去取是 403。所以缺价商品在哪一页就得开哪一页。
// - 列表接口（开页）和价格接口不是各管各的。记录到的情况：任何一个接口 403 之后，隔 17、20、27 分钟取价都还是 403，
//   隔 55、69 分钟才通（样本不多，是推断）。所以不管哪个被挡，都关掉这一页、静默 Q.blockWait 再重新开页；
//   连着 Q.maxBlocked 次还被挡就整个停下。同一个 iframe 里连着第三次 403，京东会把它跳去别的域名（多半是验证页）。
// - 开页间隔 Q.pageGap：jd_crawl.js 留下的 126 次开页记录（localStorage.__jd_hist，10-11～12）里，隔 10～16 分钟开的通了五成多，
//   隔 26～31 分钟开的 22 次通了 19 次。被挡之后多等并不更容易开页（隔 31 分钟以上再开的 9 次只通了 3 次，隔 16～27 分钟的
//   13 次通了 9 次）；换一个分类也一样被挡，不是哪一页有问题。静默 Q.blockWait 为的是取价，不是开页。
// - 同一页上的几批之间隔 Q.gap。
// - 缺价商品多的页先开；cfg.defer 里的页（cid:页码）挪到最后。
// 结果存 localStorage.__jd_prices（sku → {sam, jd}；接口通了但没给价的记空的），
// 同时往 __jd_rows 末尾追加带价格的行——jd_transfer.js 落盘后，jd.py 去重时会把价格并进去。
(() => {
  if (window.__jdp && !window.__jdp.done) window.__jdp.stopped = window.__jdp.stopped || '被新的一轮替换';
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const hhmmss = () => new Date().toTimeString().slice(0, 8);
  const load = k => { try { return JSON.parse(localStorage.getItem(k) || 'null'); } catch (e) { return null; } };
  const num = s => { const m = String(s || '').match(/\d+(\.\d+)?/); return m ? m[0] : ''; };
  const SIZE = 24, LIST_MOD = '304231119';
  const cfg = load('__jdp_cfg') || {};
  const Q = window.__jdp = {got: 0, calls: 0, pages: 0, left: 0, cur: '', stopped: null, done: false, log: load('__jdp_log') || [], waitingUntil: 0, blocked: 0,
                            gap: cfg.gap || 240000, pageGap: cfg.pageGap || 1620000, blockWait: cfg.blockWait || 3720000, maxBlocked: cfg.maxBlocked || 8,
                            lastOpen: +(localStorage.getItem('__jdp_last_open') || 0)};
  const nap = async ms => { Q.waitingUntil = Date.now() + ms; while (!Q.stopped && Date.now() < Q.waitingUntil) await sleep(Math.min(1000, Q.waitingUntil - Date.now())); Q.waitingUntil = 0; };
  const note = (...a) => { Q.log.push([hhmmss(), ...a]); if (Q.log.length > 200) Q.log.shift(); localStorage.setItem('__jdp_log', JSON.stringify(Q.log)); };
  // 还没有价格的商品（每个编号一条；优先留带 enc 的那条——页码是按带 enc 的行数出来的）
  const pending = () => {
    const rows = load('__jd_rows') || [], prices = load('__jd_prices') || {};
    const priced = new Set(rows.filter(r => r.sam).map(r => r.sku));
    const need = new Map();
    rows.forEach(r => { if (r.sku && !priced.has(r.sku) && !prices[r.sku] && (!need.has(r.sku) || (r.enc && !need.get(r.sku).enc))) need.set(r.sku, r); });
    return [...need.values()];
  };
  const record = (batch, got) => {
    const prices = load('__jd_prices') || {}, rows = load('__jd_rows') || [];
    batch.forEach(r => {
      const p = got[r.sku] || {sam: '', jd: ''};
      prices[r.sku] = p;
      if (p.sam) rows.push(Object.assign({}, r, {sam: p.sam, jd: p.jd, enc: ''}));
    });
    localStorage.setItem('__jd_prices', JSON.stringify(prices)); localStorage.setItem('__jd_rows', JSON.stringify(rows));
    Q.got += batch.filter(r => (got[r.sku] || {}).sam).length;
  };
  const trim = d => d.querySelectorAll('.m_render_structure').forEach(e => { if (e.getAttribute('m_render_instance_id') !== LIST_MOD) e.remove(); });
  // 在隐藏 iframe 里打开一个分类页，等列表出来，摘掉所有价格节点的标记。
  async function openPage(cid, page) {
    const f = document.createElement('iframe');
    f.style.cssText = 'position:absolute;left:-9999px;top:0;width:1200px;height:40px;border:0';
    f.src = `https://mall.jd.com/view_search-633676-${cid}-1-1-${SIZE}-${page}.html`;
    document.body.appendChild(f);
    let mo = null, watched = null;
    const hook = setInterval(() => {
      let d = null; try { d = f.contentDocument; } catch (e) { clearInterval(hook); return; }
      if (!d || d === watched || d.URL === 'about:blank') return;
      watched = d; trim(d);
      mo = new MutationObserver(() => trim(d)); mo.observe(d, {childList: true, subtree: true});
    }, 2);
    await new Promise(res => { f.onload = res; setTimeout(res, 15000); });
    clearInterval(hook); if (mo) mo.disconnect();
    let lis = [], total = null, d = null, api = [];
    const deadline = Date.now() + 25000;
    while (Date.now() < deadline) {
      await sleep(500);
      try { d = f.contentDocument; } catch (e) { d = null; break; }
      if (!d || !d.body) continue;
      lis = Array.from(d.querySelectorAll('li')).filter(li => li.querySelector('a[href*="item.jd.com"]') && !li.querySelector('.jNum'));
      const m = d.body.innerText.match(/共(\d+)条记录/); total = m ? +m[1] : total;
      try { api = f.contentWindow.performance.getEntriesByType('resource').filter(e => /moduleHtmlColor/.test(e.name)).map(e => e.responseStatus || 0); } catch (e) {}
      if (total === null && api.length && api.every(s => s >= 400)) break;
      if (total !== null && lis.length >= Math.min(total - (page - 1) * SIZE, SIZE)) break;
    }
    let href = ''; try { href = f.contentWindow.location.href; } catch (e) { href = 'cross-origin'; }
    if (!/view_search/.test(href) || total === null || typeof f.contentWindow.JD_local_price !== 'function') {
      f.remove();
      return {err: !/view_search/.test(href) ? '没打开' : api.some(s => s >= 400) ? '403' : '没出列表', api};
    }
    d.querySelectorAll('span[jshop="price"]').forEach(n => n.removeAttribute('jshop'));
    const bySku = {};
    lis.forEach(li => { const a = li.querySelector('a[href*="item.jd.com"]'); const sku = (a.href.match(/item\.jd\.com\/(\d+)\.html/) || [])[1]; if (sku) bySku[sku] = li; });
    return {f, d, w: f.contentWindow, bySku, total};
  }
  const priceCalls = w => { try { return w.performance.getEntriesByType('resource').filter(e => /mGetsByColor/.test(e.name)).map(e => e.responseStatus || 0); } catch (e) { return null; } };
  // 让页面给这一批商品（这一页上现成的节点）取一次价。返回 'ok' / 'blocked' / 'stop'。
  async function call(pg, batch) {
    const nodes = batch.map(r => { const li = pg.bySku[r.sku]; return {sku: r.sku, jd: li.querySelector('span[jdprice]'), sp: li.querySelector('span[jspprice]')}; }).filter(x => x.jd);
    const n0 = (priceCalls(pg.w) || []).length;
    nodes.forEach(x => { x.jd.setAttribute('jshop', 'price'); if (x.sp) x.sp.setAttribute('jshop', 'price'); });
    try { pg.w.JD_local_price(pg.w.jQuery(pg.d.body)); } catch (e) { Q.stopped = 'JD_local_price 出错：' + e; return 'stop'; }
    const val = x => ({sam: num(x.sp && x.sp.innerText), jd: num(x.jd.innerText)});
    for (let i = 0; i < 30 && !nodes.every(x => { const v = val(x); return v.sam || v.jd; }); i++) await sleep(500);
    await sleep(800);
    const all = priceCalls(pg.w);
    if (all === null) { Q.stopped = '取价后 iframe 被带到别的域名（多半是验证页）：' + Q.cur; return 'stop'; }
    const got = {}; nodes.forEach(x => { got[x.sku] = val(x); x.jd.removeAttribute('jshop'); if (x.sp) x.sp.removeAttribute('jshop'); });
    const st = all.slice(n0), filled = Object.values(got).filter(p => p.sam || p.jd).length;
    Q.calls += st.length;
    note('价', batch[0].sub + (batch.length > 1 ? '…' : ''), `${filled}/${batch.length}`, st.join(','));
    if (!st.length && !filled) { Q.stopped = '页面没有发出取价请求：' + Q.cur; return 'stop'; }
    if (filled || st.every(s => s === 200)) { record(batch, got); return 'ok'; }
    return 'blocked';
  }
  // 被挡一次（开页或取价）：静默 Q.blockWait；连着 Q.maxBlocked 次就整个停下。
  async function blocked(what) {
    if (++Q.blocked >= Q.maxBlocked) { Q.stopped = `连着 ${Q.blocked} 次被挡（每次间隔 ${Math.round(Q.blockWait / 60000)} 分钟）：${what}`; return; }
    await nap(Q.blockWait + Math.random() * 30000);
  }
  Q.run = (async () => {
    if (window.__jdpStartDelay) { const d = window.__jdpStartDelay; window.__jdpStartDelay = 0; await nap(d); }
    const totals = load('__jd_totals') || {}, cats = (load('__jd_cats') || []).filter(c => c.level === 2);
    const targets = [];
    cats.forEach(c => { for (let p = 1; p <= Math.max(1, Math.ceil((totals[c.id] || 0) / SIZE)); p++) targets.push({cid: c.id, page: p, name: `${c.top}/${c.sub} p${p}`}); });
    const tried = new Set(load('__jdp_tried') || []);            // 取完的页不再开
    // 每个商品在它那个分类的第几页：按只抓列表那一轮（带 enc 的行）的先后顺序数，省得把没有缺价商品的页也打开
    const pageOf = {}, order = {};
    (load('__jd_rows') || []).forEach(r => { if (!r.enc) return; const o = order[r.cid] = order[r.cid] || []; if (!o.includes(r.sku)) o.push(r.sku); });
    Object.keys(order).forEach(cid => order[cid].forEach((sku, i) => { pageOf[cid + ':' + sku] = Math.floor(i / SIZE) + 1; }));
    const onPage = (r, t) => r.cid === t.cid && (pageOf[t.cid + ':' + r.sku] || t.page) === t.page;
    const pend = pending(), miss = new Map(targets.map(t => [t, pend.filter(r => onPage(r, t)).length]));
    const defer = new Set(cfg.defer || []);
    targets.sort((a, b) => miss.get(b) - miss.get(a));           // 每开一页都不容易：缺得多的先取
    targets.sort((a, b) => defer.has(a.cid + ':' + a.page) - defer.has(b.cid + ':' + b.page));
    for (const t of targets) {
      if (Q.stopped) return;
      Q.left = pending().length;
      if (!Q.left) break;
      if (tried.has(t.cid + ':' + t.page) || !pending().some(r => onPage(r, t))) continue;
      Q.cur = t.name;
      for (let fails = 0; ;) {                                     // 这一页取完为止；被挡就关掉、静默之后重新开
        const wait = Q.lastOpen + Q.pageGap - Date.now();
        if (wait > 0) await nap(wait);
        if (Q.stopped) return;
        Q.lastOpen = Date.now(); localStorage.setItem('__jdp_last_open', String(Q.lastOpen));
        const pg = await openPage(t.cid, t.page);
        Q.pages++;
        note('开页', t.name, pg.err || 'ok', (pg.api || []).join(','));
        if (pg.err === '403') { await blocked('开页 ' + t.name); if (Q.stopped) return; continue; }
        if (pg.err) {                                              // 没打开 / 没出列表：按开页间隔再来，连着三次就停
          if (++fails >= 3) { Q.stopped = '分类页连着三次打不开：' + t.name; return; }
          continue;
        }
        Q.pg = pg;
        await nap(45000);
        let r = 'ok';
        while (r === 'ok' && !Q.stopped) {
          const batch = pending().filter(x => pg.bySku[x.sku]).slice(0, 10);
          if (!batch.length) break;
          r = await call(pg, batch);
          if (r === 'ok') { Q.blocked = 0; await nap(Q.gap + Math.random() * 10000); }
        }
        pg.f.remove();
        if (Q.stopped || r === 'stop') return;
        if (r === 'blocked') { await blocked('取价 ' + t.name); if (Q.stopped) return; continue; }
        break;
      }
      tried.add(t.cid + ':' + t.page); localStorage.setItem('__jdp_tried', JSON.stringify([...tried]));
    }
    Q.left = pending().length;
    Q.done = true;
    note('完', `还缺 ${Q.left} 个`);
  })().catch(e => { Q.stopped = 'JS 错误：' + e; });
  return {left: pending().length, gap: Q.gap, pageGap: Q.pageGap, blockWait: Q.blockWait, maxBlocked: Q.maxBlocked};
})()
