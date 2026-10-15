// 在 mall.jd.com 的任意页面里执行：把 localStorage 里抓到的商品分批送到本机接收端（jd_receiver.py）。
// 内置浏览器不让京东页面直接请求 127.0.0.1，所以整页跳到中转页，数据放在 # 后面；
// 中转页标题变成 jd-recv {"saved": N} 后，回到京东页面再执行一次，直到返回 done。
(() => {
  const rows = JSON.parse(localStorage.getItem('__jd_rows') || '[]');
  const sent = +(localStorage.getItem('__jd_sent') || 0);
  if (sent >= rows.length) return {done: true, total: rows.length};
  const batch = rows.slice(sent, sent + 100);
  localStorage.setItem('__jd_sent', String(sent + batch.length));
  location.href = 'http://127.0.0.1:8765/recv#' + encodeURIComponent(JSON.stringify(batch));
  return {sending: batch.length, from: sent, total: rows.length};
})()
