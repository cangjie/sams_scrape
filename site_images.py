"""山姆商品查询 H5 的商品图：京东主图缩成两种尺寸，其余从 App 截图里裁（设计文档第 7 节）。"""
import difflib
import hashlib
import io
import json
from pathlib import Path

from PIL import Image

import scrape

ROOT = Path(__file__).resolve().parent
SHOTS = scrape.DATA / "shots"
OCR_DIR = ROOT / "cache" / "ocr"                    # 截图的识别结果，按截图内容缓存
JD_SIZES = {"t": 200, "l": 600}
CARD_IMG = scrape.LIST_X_MIN - scrape.IMG_X_MIN     # 商品图那一列的宽度（基准布局坐标，85）
IMG_ABOVE = 14                                      # 商品图上沿在标题上方多少（基准布局坐标）
WHITE = 245                                         # 比这更白的算背景
TEXT_X = scrape.LIST_X_MIN + 15                     # 标题行要伸进文字列
LINE_X_MIN = 140                                    # 再往左是图片列里的角标、「补货中」
PRICE_BELOW = 110                                   # 价格在标题下方多远以内（基准布局坐标）
SECOND_LINE = (8, 30)                               # 标题折行的第二行在第一行下方多远
SIBLING_GAP = 30                                    # 两个候选行相距超过这么多，才算不同的卡


def jpeg_bytes(im, quality=82):
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()


def named(pid, data):
    """文件名 <商品 id>-<内容指纹前 8 位>.jpg：图片一变文件名就变，CDN 不会给旧图。"""
    return f"{pid}-{hashlib.sha1(data).hexdigest()[:8]}.jpg"


def jd_versions(src):
    """京东主图 → {"t": 200×200 的 JPEG, "l": 600×600 的 JPEG}"""
    im = Image.open(src).convert("RGB")
    return {k: jpeg_bytes(im.resize((n, n), Image.LANCZOS)) for k, n in JD_SIZES.items()}


def trim_square(im):
    """切掉四周的白边，再用白色补成正方形，商品居中。整张都是白的返回 None。"""
    mask = im.convert("L").point(lambda v: 0 if v > WHITE else 255)
    box = mask.getbbox()
    if not box:
        return None
    im = im.convert("RGB").crop(box)
    side = max(im.size)
    out = Image.new("RGB", (side, side), "white")
    out.paste(im, ((side - im.size[0]) // 2, (side - im.size[1]) // 2))
    return out


def ocr_raw(path):
    """截图的识别结果（bin/analyze 的原始输出），缓存在 cache/ocr/ 下。
    缓存里记着截图内容的指纹：重新抓取后同名截图内容变了，会重新识别。识别失败返回 None，不缓存。"""
    sha = hashlib.sha1(path.read_bytes()).hexdigest()
    cache = OCR_DIR / (str(path.relative_to(SHOTS)) + ".json")
    if cache.exists():
        saved = json.loads(cache.read_text(encoding="utf-8"))
        if saved.get("sha1") == sha:
            return saved["raw"]
    raw = scrape.analyze_raw(path)
    if raw is None:
        return None
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"sha1": sha, "raw": raw}, ensure_ascii=False), encoding="utf-8")
    return raw


def head_score(line, title):
    """line 是识别出的一行、title 是商品标题（都已 scrape.norm）。标题的开头出现在这一行里有多像（0～1）。
    行前面可以多几个字（「自提」「仅餐吧可售」、图片上的字和标题并成了一行），行也可以只有标题的前半截（标题折行）。"""
    best = 0.0
    for s in range(len(line)):
        sub = line[s:]
        if len(sub) < (3 if s == 0 else 4):
            break
        best = max(best, difflib.SequenceMatcher(None, sub, title[:len(sub)]).ratio())
    return best


def is_price_line(l):
    """红色或以 ¥ 开头的价格行。规格里的「450ml」不算。"""
    return (scrape.kind(l) == "red" or l["text"][:1] in "¥￥") and scrape.price_of(l) is not None


def title_text(page, l):
    """一张卡的标题：第一行 l，加上紧挨在它下面的黑字行（标题折行）。"""
    below = sorted((x for x in page.lines if x is not l and SECOND_LINE[0] < x["y"] - l["y"] < SECOND_LINE[1]
                    and LINE_X_MIN <= x["x"] < scrape.LIST_X_MAX and scrape.kind(x) == "black"),
                   key=lambda x: (x["y"], x["x"]))
    return l["text"] + "".join(x["text"] for x in below)


def full_score(text, title):
    """整段标题（都已 scrape.norm）和商品标题有多像（0～1）；标题前面可以多几个字（「线上专享」等标签）。"""
    best = 0.0
    for s in range(len(text)):
        sub = text[s:]
        if len(sub) < 4:
            break
        best = max(best, difflib.SequenceMatcher(None, sub, title).ratio())
    return best


def locate_card(page, title, price):
    """在一页截图里找这个商品的卡，返回 {"y": 标题行的 y}（基准布局坐标）；找不到或拿不准返回 None。

    不用 scrape.parse_cards：它的规则是按 Mac mini 的识别结果调的，换台机器（这台 Intel 笔记本，macOS 13）
    价格行矮了一点、标题横坐标差了一点就整张卡丢掉。这里只要求：
    - 标题的开头出现在某一行里（相似度 ≥ 0.8），这一行伸进文字列；
    - 这行下方有同样的价格；或者价格没对上但标题相似度 ≥ 0.9（全球购的卡在这台机器上识别不出价格）。
    - 另一张卡的第一行一样像、价格也一样（同系列的几款，如 ASKO 烘衣机 / 洗衣机都是 ¥9,999）：
      把标题第二行拼上再比；还分不出来就不配图——占位图比别人的图好；
    - 商品图完整露出：上沿在表头下面，下沿在底部标签栏上面。"""
    hdr, tab = page.header(), page.tab_y()
    if hdr is None or tab is None:
        return None
    top, n = hdr["y"] + hdr["h"], scrape.norm(title)
    prices = [p for p in page.lines if is_price_line(p)]
    cands = []
    for l in page.lines:
        if l["x"] < LINE_X_MIN or l["x"] >= scrape.LIST_X_MAX or l["x"] + l["w"] < TEXT_X:
            continue
        r = head_score(scrape.norm(l["text"]), n)
        if r < 0.8:
            continue
        price_ok = any(0 < p["y"] - l["y"] < PRICE_BELOW and scrape.price_of(p) == price for p in prices)
        if price_ok or r >= 0.9:
            cands.append((price_ok, r, l))
    if not cands:
        return None
    cands.sort(key=lambda c: (c[0], c[1]), reverse=True)
    price_ok, r, l = cands[0]
    rivals = [c for c in cands[1:] if c[0] == price_ok and c[1] >= r - 0.02 and abs(c[2]["y"] - l["y"]) > SIBLING_GAP]
    if rivals:
        scored = sorted(((full_score(scrape.norm(title_text(page, c[2])), n), c[2]) for c in [cands[0]] + rivals),
                        key=lambda x: x[0], reverse=True)
        if scored[1][0] >= scored[0][0] - 0.02:
            return None
        l = scored[0][1]
    y0 = l["y"] - IMG_ABOVE
    if y0 < top or y0 + CARD_IMG > tab:
        return None
    return {"y": round(l["y"])}


def crop_card(shot_img, card):
    """裁出这张卡左边的商品图：从标题上方 IMG_ABOVE 开始，宽高都是 CARD_IMG（基准布局坐标）。"""
    sx, sy = shot_img.size[0] / scrape.BASE_W, shot_img.size[1] / scrape.BASE_H
    y0 = card["y"] - IMG_ABOVE
    box = (round(scrape.IMG_X_MIN * sx), round(y0 * sy),
           round(scrape.LIST_X_MIN * sx), round((y0 + CARD_IMG) * sy))
    return trim_square(shot_img.crop(box))


def crop_for(product):
    """给一个 App 商品从截图里裁图：依次试它每条记录的截图，返回 JPEG 字节；都裁不出来返回 None。"""
    for m in product["members"]:
        path = SHOTS / m["shot"]
        if not path.exists():
            continue
        raw = ocr_raw(path)
        if raw is None:
            continue
        card = locate_card(scrape.Page(raw, path), m["title"], m["price"])
        if card is None:
            continue
        im = crop_card(Image.open(path).convert("RGB"), card)
        if im is not None:
            return jpeg_bytes(im, quality=88)
    return None
