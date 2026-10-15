#!/usr/local/bin/python3
"""京东「山姆会员商店官方旗舰店」的商品：整理抓取结果、下载商品图片。

数据来源：在已登录京东的浏览器里按店内分类逐页读商品列表（见 jd_receiver.py），
每条落在 data/jd_items.jsonl：sku、name、sam（山姆会员价）、img（图片路径）、top/sub（店内分类）、ev（评价数）。

用法：
  jd.py status            看抓到多少、缺什么
  jd.py images            下载商品主图到 data/jd_images/<sku>.jpg（800 像素；已有的跳过）
导出 Excel 由 scrape.py export 统一做（商品表里多一个「京东山姆店」sheet）。
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
JD_ITEMS = DATA / "jd_items.jsonl"
JD_IMAGES = DATA / "jd_images"
IMG_HOST = "https://img10.360buyimg.com/n0/"        # n0 = 800×800 主图


def jd_items():
    """去重后的京东商品。同一商品可能挂在多个店内分类下：保留第一次出现的分类，其余记到 also。"""
    out, idx = [], {}
    if not JD_ITEMS.exists():
        return out
    for line in JD_ITEMS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if not r.get("sku"):
            continue
        cat = (r.get("top", ""), r.get("sub", ""))
        if r["sku"] in idx:
            it = idx[r["sku"]]
            if cat != (it["top"], it["sub"]) and cat not in it["also"]:
                it["also"].append(cat)
            if not it.get("sam") and r.get("sam"):
                it["sam"] = r["sam"]
            continue
        r["also"] = []
        idx[r["sku"]] = r
        out.append(r)
    return out


def image_path(it):
    return JD_IMAGES / f"{it['sku']}.jpg"


def download(it):
    dst = image_path(it)
    if dst.exists() and dst.stat().st_size > 2000:
        return "有"
    if not it.get("img") or not it["img"].startswith("jfs/"):
        return "无图片地址"
    tmp = dst.with_suffix(".part")
    r = subprocess.run(["curl", "-s", "-m", "40", "--retry", "2", "-o", str(tmp), "-w", "%{http_code}",
                        IMG_HOST + it["img"]], capture_output=True, text=True)
    if r.stdout.strip() == "200" and tmp.exists() and tmp.stat().st_size > 2000:
        tmp.replace(dst)
        return "下载"
    tmp.unlink(missing_ok=True)
    return f"失败({r.stdout.strip()})"


def cmd_images():
    items = jd_items()
    JD_IMAGES.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(4) as pool:
        res = list(pool.map(download, items))
    counts = {}
    for x in res:
        counts[x] = counts.get(x, 0) + 1
    size = sum(f.stat().st_size for f in JD_IMAGES.glob("*.jpg"))
    print(f"{len(items)} 个商品；图片：{counts}；目录共 {size / 1e6:.1f} MB → {JD_IMAGES}")
    for it, x in zip(items, res):
        if x.startswith("失败") or x == "无图片地址":
            print("  ", x, it["sku"], it["name"][:30])


def cmd_status():
    items = jd_items()
    cats = {}
    for it in items:
        cats.setdefault(it["top"], 0)
        cats[it["top"]] += 1
    print(f"{len(items)} 个商品（去重后）；无山姆会员价 {sum(1 for i in items if not i.get('sam'))} 个；"
          f"已有图片 {sum(1 for i in items if image_path(i).exists())} 张")
    for k, v in cats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    {"images": cmd_images, "status": cmd_status}.get(sys.argv[1] if len(sys.argv) > 1 else "status", cmd_status)()
