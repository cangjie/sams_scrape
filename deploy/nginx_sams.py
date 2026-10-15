"""在 mini 服务器的 nginx 配置里加上 / 删掉山姆商品查询的转发规则（设计文档 8.2）。
  python3 nginx_sams.py add <配置文件> <锚点行> <DNS>   规则插在锚点行前面，缩进和锚点行一样
  python3 nginx_sams.py remove <配置文件>               删掉加上的规则（撤回）
在服务器上：ssh … "sudo python3 - add …" < deploy/nginx_sams.py。只改文本，不重载 nginx：改完要 nginx -t 再 reload。"""
import sys

BEGIN = "# >>> 山姆商品查询 H5（sams_scrape 仓库 deploy/nginx_sams.py，2026-10-15）"
END = "# <<< 山姆商品查询 H5"
RULES = """location = /sams { return 301 /sams/; }
location ^~ /sams/ {
    resolver %s valid=300s ipv6=off;
    set $sams_origin img.snowmeet.top;
    rewrite ^/sams/$ /upload/sams/index.html break;
    rewrite ^/sams/(.*)$ /upload/sams/$1 break;
    proxy_pass https://$sams_origin;
    proxy_set_header Host img.snowmeet.top;
    proxy_ssl_server_name on;
    proxy_ssl_name img.snowmeet.top;
}"""


def add(text, anchor, dns):
    if BEGIN in text or "/sams" in text:
        raise SystemExit("配置里已经有 /sams 的规则，没改")
    n = text.count(anchor)
    if n != 1:
        raise SystemExit(f"锚点行在文件里出现了 {n} 次，必须正好 1 次，没改")
    i = text.index(anchor)
    start = text.rfind("\n", 0, i) + 1
    indent = text[start:i]
    if indent.strip():
        raise SystemExit("锚点前面还有别的文字，要用一整行（去掉行首空格），没改")
    lines = [BEGIN] + (RULES % dns).split("\n") + [END, ""]
    block = "".join(indent + l + "\n" if l else "\n" for l in lines)
    return text[:start] + block + text[start:]


def remove(text):
    if BEGIN not in text:
        raise SystemExit("配置里没有山姆的规则，没改")
    start = text.rfind("\n", 0, text.index(BEGIN)) + 1
    end = text.index("\n", text.index(END)) + 1
    if text[end:end + 1] == "\n":
        end += 1
    return text[:start] + text[end:]


def main():
    cmd, path = sys.argv[1], sys.argv[2]
    text = open(path, encoding="utf-8").read()
    if cmd == "add":
        text = add(text, sys.argv[3], sys.argv[4])
    elif cmd == "remove":
        text = remove(text)
    else:
        raise SystemExit(__doc__)
    open(path, "w", encoding="utf-8").write(text)
    print("已改：", path)


if __name__ == "__main__":
    main()
