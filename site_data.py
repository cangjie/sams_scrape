"""山姆商品查询 H5 的数据：把去重后的 App 商品整理成网页要的 JSON。
结构见 docs/superpowers/specs/2026-10-15-sams-h5-design.md 第 6 节。这里只做计算，不读写文件。"""
import re

import scrape

TAG_SPLIT = re.compile(r"[｜|]|\s+")
TAG_TRIM = " ：:】【[]「」|｜"           # OCR 常把标签边上的竖线、括号一起认进来


def product_id(product):
    """商品 id：a + 合并进来的各条记录里最小的 id。重新生成时保持不变。"""
    return f"a{min(m['id'] for m in product['members'])}"


def split_tags(tags):
    """标签拆成小块、去掉边上的符号并去重：「进口｜限购6件」→ 进口、限购6件。「单位价 ¥2.6/瓶」整个保留。"""
    out = []
    for t in tags:
        for part in ([t] if t.startswith("单位价") else TAG_SPLIT.split(t)):
            part = part.strip(TAG_TRIM)
            if part and part not in out:
                out.append(part)
    return out


def out_of_stock(product):
    return bool(product.get("oos")) or any(w in t for t in product.get("tags", []) for w in scrape.STOCK_WORDS)


def product_cats(product, known=None):
    """商品所在的 (大类, 子分类)，第一个是主分类。合并进来的每条记录的分类，以及记录上「也在」的子分类都算。
    known（抓取时 state.json 的 {(大类, 子分类): 序号}）给出时，不在里面的「也在」子分类不算：那是改子分类前
    留下的旧名字，有的是 OCR 认错的（「服饰家纺/維包/鞋配」「营养保健/旨骼健康」）。"""
    out = []
    for m in product["members"]:
        for i, sub in enumerate([m["sub"]] + list(m.get("also", []))):
            key = (m["top"], sub)
            if not sub or key in out or (i > 0 and known is not None and key not in known):
                continue
            out.append(key)
    return out


def categories(products, top_order, sub_order):
    """分类表 [{name, subs: [{name, n}]}]，和 {(大类, 子分类): (大类序号, 子分类序号)}。
    顺序按抓取时的顺序；没有商品的子分类不列。"""
    counts = {}
    for p in products:
        for key in product_cats(p, sub_order):
            counts[key] = counts.get(key, 0) + 1
    tops = sorted({t for t, _ in counts}, key=lambda t: (top_order.index(t) if t in top_order else 99, t))
    cats, index = [], {}
    for ti, top in enumerate(tops):
        subs = sorted((s for t, s in counts if t == top), key=lambda s: (sub_order.get((top, s), 999), s))
        cats.append({"name": top, "subs": [{"name": s, "n": counts[(top, s)]} for s in subs]})
        for si, s in enumerate(subs):
            index[(top, s)] = (ti, si)
    return cats, index


def to_item(product, index, image):
    """一个商品的 JSON。image 是 (缩略图路径, 大图路径) 或 None。"""
    name, spec = scrape.split_spec(product["title"])
    return {
        "id": product_id(product),
        "n": name,
        "s": spec,
        "p": product["price"],
        "d": product.get("desc", ""),
        "t": split_tags(product.get("tags", [])),
        "x": 1 if product.get("jisuda") else 0,
        "o": 1 if out_of_stock(product) else 0,
        "c": [list(index[k]) for k in product_cats(product) if k in index],
        "it": image[0] if image else "",
        "il": image[1] if image else "",
    }


def app_date(products):
    days = sorted({m["at"][:10] for p in products for m in p["members"] if m.get("at")})
    return days[0] if len(days) == 1 else f"{days[0]}～{days[-1]}"


def build(products, top_order, sub_order, images, generated):
    """整个数据文件。images 是 {商品 id: (缩略图, 大图)}，没有图的商品不在里面。"""
    cats, index = categories(products, top_order, sub_order)
    items = [to_item(p, index, images.get(product_id(p))) for p in products]
    meta = {"app_date": app_date(products), "generated": generated, "count": len(items)}
    return {"meta": meta, "cats": cats, "items": items}


def check(data, known=None):
    """生成后的自检。返回问题列表，空列表表示通过。known 是抓取时的分类表，给出时子分类必须在里面。"""
    problems, ids, seen = [], set(), {}
    for it in data["items"]:
        if it["id"] in ids:
            problems.append(f"{it['id']} 重复")
        ids.add(it["id"])
        if not it["n"]:
            problems.append(f"{it['id']} 没有商品名")
        if not isinstance(it["p"], (int, float)) or it["p"] <= 0:
            problems.append(f"{it['id']} 价格不对：{it['p']}")
        if not it["c"]:
            problems.append(f"{it['id']} 没有分类")
        for ti, si in it["c"]:
            seen[(ti, si)] = seen.get((ti, si), 0) + 1
    for ti, top in enumerate(data["cats"]):
        for si, sub in enumerate(top["subs"]):
            if known is not None and (top["name"], sub["name"]) not in known:
                problems.append(f"{top['name']}/{sub['name']} 不在抓取时的分类表里")
            if seen.get((ti, si), 0) != sub["n"]:
                problems.append(f"{top['name']}/{sub['name']} 商品数 {sub['n']}，实际 {seen.get((ti, si), 0)}")
    return problems
