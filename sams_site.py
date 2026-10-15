#!/usr/local/bin/python3
"""山姆商品查询 H5：生成网站文件、发布到 S3。设计见 docs/superpowers/specs/2026-10-15-sams-h5-design.md。

用法（/usr/local/bin/python3，装有 Pillow；要识别截图，必须在命令沙箱外运行）：
  sams_site.py build      由 data/ 生成 dist/（数据文件、商品图、页面）。第一次要识别约两千张截图，之后用 cache/ocr/ 的缓存
  sams_site.py publish    把 dist/ 同步到 S3 的 upload/sams/（经美国服务器 2222 → mini 服务器）
"""
import gzip
import hashlib
import json
import random
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import compare  # noqa: E402
import jd  # noqa: E402
import scrape  # noqa: E402
import site_data  # noqa: E402
import site_images  # noqa: E402

SRC = ROOT / "site"
DIST = ROOT / "dist"
CACHE = ROOT / "cache"
HOST = "ubuntu@44.207.251.65"                         # 美国服务器，2222 端口转发到 mini 服务器的 22
SSH = ["ssh", "-o", "HostKeyAlias=161.189.64.210", "-o", "IdentitiesOnly=yes",
       "-i", str(Path.home() / ".ssh" / "id_rsa"), "-p", "2222"]
REMOTE_DIR = "sams-upload"                            # mini 服务器上的临时目录（~/sams-upload），传完删掉
BUCKET = "s3://snowmeet-uploads-673751646617-cn-northwest-1-an/upload/sams"
LONG = "public, max-age=31536000, immutable"
# 先传图片、数据、js、css，最后传 index.html：index.html 一换，它引用的新文件已经在桶里了
REMOTE_SCRIPT = f"""set -e
cd ~/{REMOTE_DIR}
R="--region cn-northwest-1"
aws s3 sync img {BUCKET}/img $R --size-only --content-type image/jpeg --cache-control "{LONG}"
aws s3 cp data {BUCKET}/data $R --recursive --content-type "application/json; charset=utf-8" --content-encoding gzip --cache-control "{LONG}"
for f in app.*.js; do aws s3 cp "$f" "{BUCKET}/$f" $R --content-type "application/javascript; charset=utf-8" --cache-control "{LONG}"; done
for f in app.*.css; do aws s3 cp "$f" "{BUCKET}/$f" $R --content-type "text/css; charset=utf-8" --cache-control "{LONG}"; done
aws s3 cp index.html {BUCKET}/index.html $R --content-type "text/html; charset=utf-8" --cache-control "no-cache"
cd ~ && rm -rf ~/{REMOTE_DIR}
"""


def fingerprint(data):
    return hashlib.sha1(data).hexdigest()[:8]


def render_index(template, css, js, data):
    for key in ("{{CSS}}", "{{JS}}", "{{DATA}}"):
        if key not in template:
            raise ValueError(f"index.html 模板里没有 {key}")
    return template.replace("{{CSS}}", css).replace("{{JS}}", js).replace("{{DATA}}", data)


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def build(out=DIST):
    if out.exists():
        shutil.rmtree(out)
    products = scrape.unique_items()
    top_order, sub_order = scrape.category_order()

    # 配上京东的商品用京东主图（一个 App 商品配上几个京东商品时，取名字最像的那个）
    jds = jd.jd_items()
    best = {}                                                # 商品下标 → (相似度, 京东商品)
    for i, k, s in compare.match(products, jds)[0]:
        if s > best.get(i, (0.0, None))[0]:
            best[i] = (s, jds[k])

    images, crops, missing = {}, [], []
    report = {"products": len(products), "jd_images": 0, "crops": 0}
    for i, p in enumerate(products):
        pid = site_data.product_id(p)
        src = jd.image_path(best[i][1]) if i in best else None
        if src is not None and src.exists():
            v = site_images.jd_versions(src)
            name = site_images.named(pid, v["l"])
            write(out / "img" / "t" / name, v["t"])
            write(out / "img" / "l" / name, v["l"])
            images[pid] = (f"img/t/{name}", f"img/l/{name}")
            report["jd_images"] += 1
        else:
            data = site_images.crop_for(p)
            if data is None:
                missing.append(f"{pid}\t{p['top']}/{p['sub']}\t{p['title']}\t{p['price']}")
            else:
                name = site_images.named(pid, data)
                write(out / "img" / "t" / name, data)
                images[pid] = (f"img/t/{name}", f"img/t/{name}")
                crops.append(out / "img" / "t" / name)
                report["crops"] += 1
        if (i + 1) % 200 == 0:
            print(f"  图片 {i + 1}/{len(products)}", flush=True)
    report["no_image"] = len(missing)

    data = site_data.build(products, top_order, sub_order, images, datetime.now().strftime("%Y-%m-%d %H:%M"))
    problems = site_data.check(data)
    problems += [f"{it['id']} 的图片不存在：{p}" for it in data["items"] for p in {it["it"], it["il"]}
                 if p and not (out / p).exists()]
    if problems:
        raise SystemExit("自检没过：\n  " + "\n  ".join(problems[:30]))

    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    data_file = f"data/products.{fingerprint(blob)}.json"
    write(out / data_file, blob)
    js = (SRC / "lib.js").read_bytes() + b"\n" + (SRC / "app.js").read_bytes()
    css = (SRC / "app.css").read_bytes()
    js_file, css_file = f"app.{fingerprint(js)}.js", f"app.{fingerprint(css)}.css"
    write(out / js_file, js)
    write(out / css_file, css)
    html = render_index((SRC / "index.html").read_text(encoding="utf-8"), css_file, js_file, data_file)
    write(out / "index.html", html.encode("utf-8"))

    CACHE.mkdir(exist_ok=True)
    (CACHE / "no_image.txt").write_text("\n".join(missing) + "\n", encoding="utf-8")
    contact_sheet(crops, CACHE / "contact_sheet.jpg")
    report["data_file"] = data_file
    return report


def contact_sheet(paths, dest, n=100, size=120):
    """随机 100 张裁出来的图拼成一张，人工抽查用。"""
    from PIL import Image
    if not paths:
        return
    pick = random.Random(15).sample(paths, min(n, len(paths)))
    cols = 10
    sheet = Image.new("RGB", (cols * size, ((len(pick) + cols - 1) // cols) * size), "white")
    for i, p in enumerate(pick):
        im = Image.open(p).convert("RGB")
        im.thumbnail((size - 6, size - 6))
        sheet.paste(im, ((i % cols) * size + 3, (i // cols) * size + 3))
    dest.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dest, quality=85)


def stage(src, dst):
    """要上传的副本：和 dist/ 一样，只是 data/*.json 换成 gzip 压缩后的字节（上传时带 Content-Encoding: gzip）。"""
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    for p in (dst / "data").glob("*.json"):
        p.write_bytes(gzip.compress(p.read_bytes(), mtime=0))


def publish():
    if not (DIST / "index.html").exists():
        raise SystemExit("dist/ 还没生成，先运行 sams_site.py build")
    staging = CACHE / "upload"
    stage(DIST, staging)
    subprocess.run(["rsync", "-rlt", "--delete", "-e", " ".join(SSH), f"{staging}/", f"{HOST}:{REMOTE_DIR}/"], check=True)
    subprocess.run(SSH + [HOST, "bash -s"], input=REMOTE_SCRIPT.encode("utf-8"), check=True)
    shutil.rmtree(staging)
    print("已同步到 https://img.snowmeet.top/upload/sams/")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "build":
        r = build()
        print(f"商品 {r['products']} 个：京东图 {r['jd_images']}，截图裁图 {r['crops']}，没有图 {r['no_image']}；"
              f"数据 {r['data_file']}")
        print(f"抽查图：{CACHE / 'contact_sheet.jpg'}；没有图的商品：{CACHE / 'no_image.txt'}")
    elif cmd == "publish":
        publish()
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
