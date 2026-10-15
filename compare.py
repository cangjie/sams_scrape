#!/usr/local/bin/python3
"""山姆 App 的商品（items.jsonl）和京东山姆店的商品（jd_items.jsonl）对比：哪些只在一边有。

两边没有共同的商品编号，只能靠「名字 + 价格 + 规格」认：
- 名字：去掉品牌前缀（Member's Mark / MM）、「××进口」、规格之后，按相邻两字的重合度打分（0～1）。
  到处都有的字眼（「葡萄酒」「酱香型白酒」）权重很低，少见的（「拓弗」「习酒」）权重高，不然同价位的红酒会互相认错。
  京东标题常常不带品牌、App 标题常常带英文品牌，所以再拿「去掉英文的名字」比一次，取高的。
- 价格：同一个商品两边的山姆会员价几乎总是一样，价格相同的话名字四五成像就认；价格不同就要名字非常像。
- 规格：标题里的数字（克数、毫升、几包……）。一边的数字包含在另一边里算规格一致；对不上算规格冲突
  （同名不同包装，比如椰子水 1L*6 和 200mL*24，当成两个商品）。
- 每个商品只认对面「最像的那个」（并列的都算——App 里同一个商品会挂在几个大类下），不是够像就都认。
京东还没取到价格的商品只能靠名字和规格，认得保守一些；取到价格之后重新导出，结果会更准。

用法：compare.py [档位下限 档位上限]   打印统计；带两个数字时列出相似度落在这一档、却没认成同一个的京东商品（调阈值时看）
导出由 scrape.py export 调 compare()，在商品表里加两个 sheet。
"""
import collections
import difflib
import math
import re
import sys
import unicodedata

VARIANTS = str.maketrans("帯島黃盞製菓縣鮮純檽", "带岛黄盏制果县鲜纯糯")    # App 标题是 OCR 出来的，常认成异体字 / 形近字
# 山姆自有品牌：App 里写 MM，京东写 Member's Mark，是一回事。「MM」常紧贴着汉字（MM烘烤混合坚果仁），但不能把 295mm 的 mm 也算进来
BRAND = re.compile(r"member['’`‘ ]?s?\s*mark|(?<![a-z0-9])mm(?![a-z])|山姆", re.I)
COUNTRY = ("法国|德国|意大利|西班牙|葡萄牙|智利|阿根廷|澳大利亚|澳洲|新西兰|美国|加拿大|墨西哥|巴西|秘鲁|英国|爱尔兰|苏格兰|荷兰|比利时|丹麦|"
           "瑞士|瑞典|挪威|芬兰|奥地利|匈牙利|波兰|希腊|土耳其|俄罗斯|南非|日本|韩国|泰国|越南|马来西亚|印度尼西亚|印尼|菲律宾|新加坡|印度|"
           "斯里兰卡|以色列")
IMPORT = re.compile(rf"(?:{COUNTRY})?(?:原装|原瓶)?进口|国产|新旧包装随机|包装随机|【[^【】]*】")
# 括号里只是品类说明的（灭菌乳、半固态调味料、发酵酒……）：京东标题总带，App 标题时带时不带，去掉再比
KIND = re.compile(r"\([^()]*(?:乳|调味|酱油|饮料|饮品|食品|制品|发酵|卫生纸|固体|型)[^()]*\)")
UNIT = (r"(?:kg|千克|公斤|克|g|毫升|ml|升|l|斤|磅|片|只|个(?!月)|枚|粒|包|袋|盒|瓶|罐|支|条|块|卷|抽|听|颗|串|份|对|套|件|枝|朵|束|盆|根|桶|箱|杯|碗|张|"
        r"度|%vol|vol|cm|mm|寸|英寸|码)")
SPEC = re.compile(r"(?:约\s*)?\d[\d.]*\s*" + UNIT + r"(?![a-z])", re.I)
MULT = re.compile(r"[*x×+]\s*\d+")
CUT = re.compile(r"\d[\d.]*\s*[a-z]*\s*(?:\.{2,}|…|⋯|\.)\s*$")            # App 标题太长被截断时，结尾那个不完整的数字
NUM = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|千克|公斤|l|升|斤)?(?:[^\d*x×]{0,3}[*x×]\s*(\d+))?", re.I)
# 尺码：京东一个尺码一条（小号 / 中号 / 大号、M 码 / L 码），App 往往只有一条「××系列」，比名字前去掉
SIZE = re.compile(r"(?<![a-z0-9])(?:x{0,3}[sml]|x{1,3}l)码?(?![a-z0-9])|[小中大]号|加大号|均码")
CODE = re.compile(r"[a-z]{1,5}\d{3,}[a-z0-9]*")                         # 型号（HX9912、PPM3505G）
SHARED_MIN = 10          # 重合部分的权重和至少这么多（差不多两个少见的字对），才把「短的包含在长的里」算成像


def _clean(t):
    return CUT.sub("", unicodedata.normalize("NFKC", t).lower().translate(VARIANTS))


def cores(title):
    """(完整的名字, 去掉英文的名字)，都只留汉字、字母、数字。"""
    t = " ".join(dict.fromkeys(_clean(title).split()))          # 京东标题后半截会把规格、尺码再写一遍，重复的词只留一个
    t = MULT.sub(" ", SPEC.sub(" ", SIZE.sub(" ", IMPORT.sub(" ", BRAND.sub(" ", KIND.sub(" ", t))))))
    full = re.sub(r"[^0-9a-z一-鿿]", "", t)
    return full, re.sub(r"[a-z]+", "", full)


def spec_nums(title):
    """(标题里出现的数字, 再加上乘出来的总量)。千克、升、斤换算成克、毫升；「100g×6」的总量是 600；不算「1 盒 / 1 瓶」这种 1。"""
    out, total = set(), set()
    for m in NUM.finditer(_clean(title)):
        v, u = float(m.group(1)), (m.group(2) or "").lower()
        v *= 1000 if u in ("kg", "千克", "公斤", "l", "升") else 500 if u == "斤" else 1
        out.add(round(v, 2))
        if m.group(3):
            out.add(float(m.group(3)))
            total.add(round(v * float(m.group(3)), 2))
    out.discard(1.0)
    return frozenset(out), frozenset(out | total)


def grams(s):
    return frozenset(s[i:i + 2] for i in range(len(s) - 1)) if len(s) > 1 else frozenset([s] if s else [])


class Side:
    def __init__(self, title, price):
        self.full, self.cjk = cores(title)
        self.mm = bool(BRAND.search(_clean(title)))             # 是不是山姆自有品牌
        self.gfull, self.gcjk = grams(self.full), grams(self.cjk)
        self.nums, self.nums_all = spec_nums(title)
        self.codes = frozenset(CODE.findall(_clean(title)))
        self.price = price

    def weigh(self, w, common):
        self.wfull, self.wcjk = sum(w[g] for g in self.gfull), sum(w[g] for g in self.gcjk)
        # 少见的规格数字（265 克、1.14 千克）差不多能当编号用；太小的数（几包、几片）不算
        self.rare = frozenset(v for v in self.nums_all - common if v >= 50)


def _sim(ga, wa, gb, wb, w):
    shared = sum(w[g] for g in ga & gb)
    if not shared:
        return 0.0
    dice = 2 * shared / (wa + wb)
    # 重合的部分够有辨识度时，「短的整个包含在长的里」也算像（一边多了品牌、产地）；只重合「啤酒」「红葡萄酒」这种不算
    return 0.6 * dice + 0.4 * shared / min(wa, wb) if shared >= SHARED_MIN else dice


def score(a, b, w):
    s = _sim(a.gfull, a.wfull, b.gfull, b.wfull, w)
    if min(len(a.cjk), len(b.cjk)) >= 4:
        s = max(s, _sim(a.gcjk, a.wcjk, b.gcjk, b.wcjk, w))
    return s


def price_same(pa, pj):
    return bool(pa and pj) and abs(pa - pj) <= max(0.05, 0.005 * pa)


def same(s, a, j):
    """a（App 商品）和 j（京东商品）是不是同一个。s 是名字的相似度。"""
    spec_ok = bool(a.nums and j.nums) and (a.nums <= j.nums_all or j.nums <= a.nums_all)
    # 规格冲突：两边都有数字、互不包含，而且重合不到一半（重合过半的多半是 OCR 认错了一个数：4g*11 / 4g*17）
    spec_bad = (bool(a.nums and j.nums) and not spec_ok
                and len(a.nums_all & j.nums_all) / len(a.nums_all | j.nums_all) < 0.4)
    eq = price_same(a.price, j.price)
    differ = bool(a.price and j.price) and not eq
    if a.codes and j.codes:                                    # 两边都写了型号：型号说了算
        return bool(a.codes & j.codes) and s >= 0.40 and not differ
    if (a.rare & j.rare) and not spec_bad and (s >= 0.20 if eq else s >= 0.40 and not differ):
        return True                                            # 少见的规格数字对上了，名字有点像就认
    # 京东标了自有品牌（Member's Mark）而 App 这条没标 MM：App 的自有品牌商品几乎都带 MM，价格又对不上的话，
    # 多半是别的牌子的同类商品（Member's Mark XO 干邑 ↔ 马爹利 XO 干邑），除非去掉品牌后名字几乎一样。
    # 反过来不设限：京东标题经常不写品牌（「有机小米 2.3kg」就是 MM 有机小米）。
    if j.mm and not a.mm and not price_same(a.price, j.price) and s < 0.90:
        return False
    if price_same(a.price, j.price):
        if spec_bad:                                           # 价格一样、规格对不上：多半是另一个包装，除非名字几乎一样（规格是 OCR 认错的）
            return s >= 0.80
        if s >= 0.45 or (spec_ok and s >= 0.30):
            return True
        # 价格、规格都一样，名字逐字比也七成像（OCR 认错了关键的那个字），或者短的那个名字的字几乎都在长的里（词序不同：软心玉米团 / 玉米软心团）
        x, y = sorted((a.cjk or a.full, j.cjk or j.full), key=len)
        return spec_ok and (difflib.SequenceMatcher(None, x, y).ratio() >= 0.7
                            or (len(x) >= 5 and sum(c in y for c in x) / len(x) >= 0.8))
    if a.price and j.price:                                    # 两边价格不一样：同名不同款 / 不同包装的可能性大
        rel = abs(a.price - j.price) / max(a.price, j.price)
        return not spec_bad and (s >= 0.95 or (s >= 0.80 and rel <= 0.15))
    return (s >= 0.66 and not spec_bad) or (s >= 0.55 and spec_ok)     # 京东还没取到价格


def note(s, app_price, jd_price_):
    """「只在一边」的商品的备注：对面最像的那个为什么没认成同一个。s 是相似度。"""
    if s >= 0.45 and not jd_price_:
        return "对面有名字相近的；京东暂无价格，补价后重判"
    if s >= 0.6:
        return "对面有名字相近的，同价但规格不同" if price_same(app_price, jd_price_) else "对面有名字相近的，但价格 / 规格不同"
    return ""


def jd_price(it):
    try:
        return float(it["sam"]) if it.get("sam") else None
    except ValueError:
        return None


def compare(app_items, jd_items):
    """返回 (只在 App 的, 只在京东的, 认成同一个的对数)。
    前两个是列表，每项 (商品, 对面最像的商品或 None, 相似度)。"""
    A = [Side(it["title"], it.get("price")) for it in app_items]
    J = [Side(it["name"], jd_price(it)) for it in jd_items]
    df = collections.Counter(g for x in A + J for g in x.gfull | x.gcjk)
    n = len(A) + len(J)
    w = {g: max(0.3, math.log(n / d) - 1.5) for g, d in df.items()}
    nf = collections.Counter(v for x in A + J for v in x.nums_all)
    common = frozenset(v for v, d in nf.items() if d > 8)
    for x in A + J:
        x.weigh(w, common)
    index = collections.defaultdict(set)
    for i, a in enumerate(A):
        for g in a.gfull | a.gcjk:
            index[g].add(i)
    ok = []                                  # 够格认成同一个的配对 (排序用的分, App 序号, 京东序号, 是不是十拿九稳：价格、规格一样且名字七成像)
    near_a, near_j = {}, {}                  # 序号 → (排序用的分, 相似度, 对面序号)：对面最像的那个，认没认上都记
    for k, j in enumerate(J):
        cand = set()
        for g in j.gfull | j.gcjk:
            cand |= index.get(g, set())
        for i in cand:
            a = A[i]
            s = score(a, j, w)
            if s < 0.15:
                continue
            eq = price_same(a.price, j.price)
            if same(s, a, j):
                # 十拿九稳：价格、规格都一样，名字七成像；或者五成像、但短名字的字几乎都在长名字里（OCR 掉字 / 认错一个字：棒岛 ↔ 棒棰岛）
                x, y = sorted((a.cjk or a.full, j.cjk or j.full), key=len)
                sure = (eq and bool(a.nums and j.nums) and (a.nums <= j.nums_all or j.nums <= a.nums_all)
                        and (s >= 0.70 or (s >= 0.50 and sum(c in y for c in x) / len(x) >= 0.85)))
                ok.append((s + (0.3 if eq else 0) + (0.05 if a.mm and j.mm else 0), i, k, sure))
            rank = s + (0.2 if eq else 0)
            if rank > near_a.get(i, (0,))[0]:
                near_a[i] = (rank, s, k)
            if rank > near_j.get(k, (0,))[0]:
                near_j[k] = (rank, s, i)
    # 从最像的一对开始认。一个商品认上之后，只再接受跟它那一对差不多像的、或者十拿九稳的（App 里同一商品挂在几个大类下、京东的 M/L 码）；
    # 最像的对象被别人认走了的，还能退而认下一个够格的（12 年威士忌 ↔ 12 年威士忌，而不是都挤到普通款上）。
    pairs, got_a, got_j = [], {}, {}
    for r, i, k, sure in sorted(ok, reverse=True):
        if sure or (r >= got_a.get(i, 0) - 0.15 and r >= got_j.get(k, 0) - 0.15):
            pairs.append((i, k))
            got_a.setdefault(i, r)
            got_j.setdefault(k, r)
    hit_a, hit_j = {i for i, _ in pairs}, {k for _, k in pairs}
    app_only = [(it, jd_items[near_a[i][2]] if i in near_a else None, near_a[i][1] if i in near_a else 0.0)
                for i, it in enumerate(app_items) if i not in hit_a]
    jd_only = [(it, app_items[near_j[k][2]] if k in near_j else None, near_j[k][1] if k in near_j else 0.0)
               for k, it in enumerate(jd_items) if k not in hit_j]
    return app_only, jd_only, len(pairs)


if __name__ == "__main__":
    import jd
    import scrape
    app, jds = scrape.merged_items(), jd.jd_items()
    app_only, jd_only, pairs = compare(app, jds)
    print(f"App {len(app)} 个，京东 {len(jds)} 个（其中 {sum(1 for x in jds if not x.get('sam'))} 个还没有价格）")
    print(f"只在 App：{len(app_only)}；只在京东：{len(jd_only)}；两边都有：App {len(app) - len(app_only)} 个 / 京东 {len(jds) - len(jd_only)} 个（{pairs} 对）")
    if len(sys.argv) > 2:
        lo, hi = float(sys.argv[1]), float(sys.argv[2])
        for it, near, s in jd_only:
            if near and lo <= s < hi:
                print(f"{s:.2f} | 京东 {it['name'][:36]!r} [{it.get('sam', '')}] ↔ App {near['title'][:36]!r} [{near['price']}]")
