#!/usr/local/bin/python3
"""京东山姆店抓取的本机接收端。

商品数据是在浏览器里的京东页面上读出来的（要登录状态），量大，不适合经对话传回来；
页面把每一页的结果 POST 到这里，这里逐行追加到 data/jd_items.jsonl。只监听 127.0.0.1。

用法：jd_receiver.py [端口=8765]
"""
import json
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

OUT = Path(__file__).resolve().parent / "data" / "jd_items.jsonl"
ORIGIN = "https://mall.jd.com"


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        # 中转页：内置浏览器不让京东页面直接请求 127.0.0.1，所以让那个标签页整页跳到这里，
        # 数据放在 URL 的 # 后面（不会发给服务器），由本页脚本读出来再同源 POST 给 /save。
        page = """<!doctype html><meta charset="utf-8"><title>jd-recv</title><body>receiving…<script>
(async () => {
  let payload = '';
  try { payload = decodeURIComponent(location.hash.slice(1)); } catch (e) {}
  if (!payload && window.name && window.name[0] === '[') payload = window.name;
  let res = 'empty';
  if (payload) {
    const r = await fetch('/save', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: payload});
    res = await r.text();
  }
  document.title = 'jd-recv ' + res;
  document.body.innerText = 'result: ' + res + ' | bytes=' + payload.length;
  history.replaceState(null, '', '/recv');
})();
</script>"""
        body = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            rows = json.loads(body.decode("utf-8"))
            assert isinstance(rows, list)
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            OUT.parent.mkdir(parents=True, exist_ok=True)
            with open(OUT, "a", encoding="utf-8") as f:
                for r in rows:
                    r["at"] = stamp
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            code, msg = 200, {"saved": len(rows)}
        except Exception as e:                                  # noqa: BLE001
            code, msg = 400, {"error": str(e)}
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(msg).encode("utf-8"))

    def log_message(self, fmt, *args):
        print(datetime.now().strftime("%H:%M:%S"), fmt % args, flush=True)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"listening on 127.0.0.1:{port} → {OUT}", flush=True)
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
