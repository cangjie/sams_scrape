#!/usr/local/bin/python3
"""京东抓取留在浏览器里的状态：导出到本机 / 从本机装回浏览器。换电脑、换浏览器时用。

抓到哪、哪些页开过、商品行、分类表、两个抓取脚本本身，都存在浏览器里 mall.jd.com 的 localStorage（__jd 开头的键）；
data/jd_items.jsonl 只是商品行的副本，光有它续不了。这里把那些键原样存成 data/jd_browser_state.json。

内置浏览器不让京东页面直接请求 127.0.0.1，所以和 jd_receiver.py 一样靠整页跳转带数据（放在 # 后面，base64，不会发给京东）。

用法：
  jd_state.py [端口=8767]    起服务，只监听 127.0.0.1
  jd_state.py js             打印下面两段要在京东页面里执行的 JS

  导出：在 mall.jd.com 的任意页面里执行 EXPORT_JS；页面跳到 /export，标题变成「jd-state saved …」就是存好了。
  装回：浏览器打开 http://127.0.0.1:8767/import，它带着状态跳到 mall.jd.com 的一个静态文件；到了之后在那个页面里执行 IMPORT_JS。
"""
import base64
import hashlib
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

STATE = Path(__file__).resolve().parent / "data" / "jd_browser_state.json"
RELAY = "https://mall.jd.com/misc/js/tab-3.js"          # 同源、很轻的静态文件：开它不占分类页的额度

EXPORT_JS = """(() => {
  const o = {}; Object.keys(localStorage).filter(k => k.startsWith('__jd')).forEach(k => { o[k] = localStorage.getItem(k); });
  let s = ''; new TextEncoder().encode(JSON.stringify(o)).forEach(c => { s += String.fromCharCode(c); });
  setTimeout(() => { location.href = 'http://127.0.0.1:%d/export#' + btoa(s); }, 200);
  return {keys: Object.keys(o).length, bytes: s.length};
})()"""

IMPORT_JS = """(() => {
  const o = JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(location.hash.slice(1)), c => c.charCodeAt(0))));
  Object.keys(o).forEach(k => localStorage.setItem(k, o[k]));
  history.replaceState(null, '', location.pathname);
  return {keys: Object.keys(o).length, rows: JSON.parse(o.__jd_rows || '[]').length, sent: o.__jd_sent};
})()"""

EXPORT_PAGE = """<!doctype html><meta charset="utf-8"><title>jd-state</title><body>saving…<script>
(async () => {
  const b64 = location.hash.slice(1);
  let res = 'empty';
  if (b64) res = await (await fetch('/state', {method: 'POST', body: b64})).text();
  document.title = 'jd-state ' + res;
  document.body.innerText = res;
  history.replaceState(null, '', '/export');
})();
</script>"""

IMPORT_PAGE = """<!doctype html><meta charset="utf-8"><title>jd-state</title><body>loading…<script>
(async () => {
  const r = await fetch('/state.b64', {cache: 'no-store'});
  const b64 = await r.text();
  if (!r.ok) { document.title = 'jd-state ' + b64; document.body.innerText = b64; return; }
  location.href = '%s#' + b64;
})();
</script>"""


def summary(state):
    rows = json.loads(state.get("__jd_rows") or "[]")
    priced = {r["sku"] for r in rows if r.get("sam")}
    return f"{len(state)} keys, {len(rows)} rows, {len({r['sku'] for r in rows} - priced)} without price"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="text/plain; charset=utf-8"):
        body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/export":
            self._send(200, EXPORT_PAGE, "text/html; charset=utf-8")
        elif path == "/import":
            self._send(200, IMPORT_PAGE % RELAY, "text/html; charset=utf-8")
        elif path == "/state.b64":
            if not STATE.exists():
                self._send(404, f"no state file: {STATE}")
                return
            state = json.loads(STATE.read_text(encoding="utf-8"))
            raw = json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self._send(200, base64.b64encode(raw).decode("ascii"))
        else:
            self._send(404, "not found")

    def do_POST(self):
        try:
            raw = base64.b64decode(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            state = json.loads(raw.decode("utf-8"))
            assert isinstance(state, dict) and all(isinstance(v, str) for v in state.values())
            STATE.parent.mkdir(parents=True, exist_ok=True)
            if STATE.exists():                                  # 留一份上一次的
                STATE.replace(STATE.with_suffix(".prev.json"))
            STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
            code, msg = 200, f"saved {summary(state)}, sha256 {hashlib.sha256(raw).hexdigest()[:16]}"
        except Exception as e:                                  # noqa: BLE001
            code, msg = 400, f"error {e}"
        self._send(code, msg)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "js":
        print("// 导出：在 mall.jd.com 的页面里执行\n" + EXPORT_JS % 8767 + "\n\n// 装回：从 /import 跳到京东之后，在那个页面里执行\n" + IMPORT_JS)
        sys.exit(0)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8767
    print(f"listening on 127.0.0.1:{port} ↔ {STATE}", flush=True)
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
