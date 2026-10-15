import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import site_data  # noqa: E402


def rec(id, top, sub, title="澳洲羔羊肉卷 1kg", price=118.0, also=(), tags=(), oos=False, jisuda=False,
        at="2026-10-10 09:00:00"):
    return dict(id=id, top=top, sub=sub, title=title, price=price, desc="卖点", tags=list(tags), also=list(also),
                oos=oos, jisuda=jisuda, at=at, shot=f"{top}/00001.png")


def product(*members):
    """模拟 scrape.unique_items 的结果。"""
    first = dict(members[0])
    first["members"] = list(members)
    first["tags"] = [t for m in members for t in m["tags"]]
    first["oos"] = any(m["oos"] for m in members)
    first["jisuda"] = any(m["jisuda"] for m in members)
    return first


TOPS = ["肉蛋果蔬", "全球购"]
SUBS = {("肉蛋果蔬", "火锅食材"): 0, ("肉蛋果蔬", "羊肉"): 1, ("全球购", "进口肉类"): 0}


class SiteDataTest(unittest.TestCase):
    def test_product_id_is_smallest_member_id(self):
        p = product(rec(7, "全球购", "进口肉类"), rec(3, "肉蛋果蔬", "羊肉"))
        self.assertEqual(site_data.product_id(p), "a3")

    def test_split_tags(self):
        tags = ["进口｜限购6件", "进口 限购6件", "全球购】", "单位价 ¥2.6/瓶", ""]
        self.assertEqual(site_data.split_tags(tags), ["进口", "限购6件", "全球购", "单位价 ¥2.6/瓶"])

    def test_out_of_stock_from_flag_or_tag(self):
        self.assertTrue(site_data.out_of_stock(product(rec(1, "肉蛋果蔬", "羊肉", oos=True))))
        self.assertTrue(site_data.out_of_stock(product(rec(1, "肉蛋果蔬", "羊肉", tags=["补货中"]))))
        self.assertFalse(site_data.out_of_stock(product(rec(1, "肉蛋果蔬", "羊肉", tags=["冷冻"]))))

    def test_product_in_several_categories(self):
        p = product(rec(1, "肉蛋果蔬", "羊肉", also=["火锅食材"]), rec(9, "全球购", "进口肉类"))
        self.assertEqual(site_data.product_cats(p),
                         [("肉蛋果蔬", "羊肉"), ("肉蛋果蔬", "火锅食材"), ("全球购", "进口肉类")])

    def test_categories_order_counts_and_index(self):
        a = product(rec(1, "肉蛋果蔬", "羊肉", also=["火锅食材"]))
        b = product(rec(2, "肉蛋果蔬", "火锅食材", title="虾滑 800g", price=89.9))
        c = product(rec(3, "全球购", "进口肉类", title="牛排 1kg", price=199.0))
        cats, index = site_data.categories([a, b, c], TOPS, SUBS)
        self.assertEqual([t["name"] for t in cats], ["肉蛋果蔬", "全球购"])
        self.assertEqual(cats[0]["subs"], [{"name": "火锅食材", "n": 2}, {"name": "羊肉", "n": 1}])
        self.assertEqual(index[("肉蛋果蔬", "羊肉")], (0, 1))
        self.assertEqual(index[("全球购", "进口肉类")], (1, 0))

    def test_to_item_fields(self):
        p = product(rec(5, "肉蛋果蔬", "羊肉", tags=["冷冻 进口"], jisuda=True))
        _, index = site_data.categories([p], TOPS, SUBS)
        it = site_data.to_item(p, index, ("img/t/a5-1.jpg", "img/l/a5-1.jpg"))
        self.assertEqual(it, {"id": "a5", "n": "澳洲羔羊肉卷", "s": "1kg", "p": 118.0, "d": "卖点",
                              "t": ["冷冻", "进口"], "x": 1, "o": 0, "c": [[0, 0]],
                              "it": "img/t/a5-1.jpg", "il": "img/l/a5-1.jpg"})

    def test_to_item_without_image(self):
        p = product(rec(5, "肉蛋果蔬", "羊肉"))
        _, index = site_data.categories([p], TOPS, SUBS)
        it = site_data.to_item(p, index, None)
        self.assertEqual((it["it"], it["il"]), ("", ""))

    def test_app_date(self):
        self.assertEqual(site_data.app_date([product(rec(1, "肉蛋果蔬", "羊肉"))]), "2026-10-10")
        two = [product(rec(1, "肉蛋果蔬", "羊肉")),
               product(rec(2, "肉蛋果蔬", "羊肉", title="虾滑", at="2026-10-12 01:00:00"))]
        self.assertEqual(site_data.app_date(two), "2026-10-10～2026-10-12")

    def test_build_and_check(self):
        a = product(rec(1, "肉蛋果蔬", "羊肉", also=["火锅食材"]))
        b = product(rec(2, "全球购", "进口肉类", title="牛排 1kg", price=199.0))
        data = site_data.build([a, b], TOPS, SUBS, {"a1": ("img/t/x.jpg", "img/t/x.jpg")}, "2026-10-15 12:00")
        self.assertEqual(data["meta"], {"app_date": "2026-10-10", "generated": "2026-10-15 12:00", "count": 2})
        self.assertEqual(data["items"][1]["it"], "")
        self.assertEqual(site_data.check(data), [])

    def test_product_cats_drops_unknown_also(self):
        """「也在」里有改子分类前留下的 OCR 错字旧名（維包/鞋配、旨骼健康），给了分类表就不算。"""
        p = product(rec(1, "肉蛋果蔬", "羊肉", also=["火锅食材", "羊肉卷错字"]))
        self.assertEqual(site_data.product_cats(p, SUBS), [("肉蛋果蔬", "羊肉"), ("肉蛋果蔬", "火锅食材")])
        self.assertEqual(len(site_data.product_cats(p)), 3)

    def test_build_ignores_unknown_sub(self):
        a = product(rec(1, "肉蛋果蔬", "羊肉", also=["羊肉卷错字"]))
        data = site_data.build([a], TOPS, SUBS, {}, "2026-10-15 12:00")
        self.assertEqual([s["name"] for s in data["cats"][0]["subs"]], ["羊肉"])
        self.assertEqual(data["items"][0]["c"], [[0, 0]])
        self.assertEqual(site_data.check(data, SUBS), [])

    def test_check_flags_unknown_sub(self):
        a = product(rec(1, "肉蛋果蔬", "羊肉"))
        data = site_data.build([a], TOPS, SUBS, {}, "2026-10-15 12:00")
        data["cats"][0]["subs"].append({"name": "羊肉卷错字", "n": 0})
        self.assertTrue(any("羊肉卷错字" in x for x in site_data.check(data, SUBS)))

    def test_check_finds_problems(self):
        a = product(rec(1, "肉蛋果蔬", "羊肉"))
        data = site_data.build([a], TOPS, SUBS, {}, "2026-10-15 12:00")
        data["items"][0]["p"] = 0
        data["cats"][0]["subs"][0]["n"] = 5
        data["items"].append(dict(data["items"][0]))
        problems = site_data.check(data)
        self.assertTrue(any("价格" in x for x in problems), problems)
        self.assertTrue(any("商品数" in x for x in problems), problems)
        self.assertTrue(any("重复" in x for x in problems), problems)


if __name__ == "__main__":
    unittest.main()
