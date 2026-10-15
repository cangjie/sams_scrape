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


def find_card(cards, title, price):
    """截图里对应这个商品的那张卡：价格相同，标题一样或八成像（同 scrape.Store.find 的规则），取最像的。"""
    n, best = scrape.norm(title), None
    for c in cards:
        if c["price"] != price:
            continue
        m = scrape.norm(c["title"])
        r = 1.0 if m == n else difflib.SequenceMatcher(None, m, n).ratio()
        if r >= 0.8 and (best is None or r > best[0]):
            best = (r, c)
    return best[1] if best else None


def visible_cards(page):
    """本页商品图完整露出的卡：图的上沿在表头下面，下沿在底部标签栏上面。"""
    hdr, tab = page.header(), page.tab_y()
    if hdr is None or tab is None:
        return []
    top = hdr["y"] + hdr["h"]
    return [c for c in scrape.parse_cards(page, at_top=True, strict=False)
            if c["y"] - IMG_ABOVE >= top and c["y"] - IMG_ABOVE + CARD_IMG <= tab]


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
        card = find_card(visible_cards(scrape.Page(raw, path)), m["title"], m["price"])
        if card is None:
            continue
        im = crop_card(Image.open(path).convert("RGB"), card)
        if im is not None:
            return jpeg_bytes(im, quality=88)
    return None
