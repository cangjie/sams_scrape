import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scrape  # noqa: E402
import site_images  # noqa: E402



def fake_page(lines):
    """基准布局（383×834）上的一页：表头「销量」在 y=257、底部标签栏在 y=778，外加给定的行 (x, y, w, 文字)。"""
    base = [(264, 257, 30, "销量"), (180, 778, 20, "发现"), (328, 779, 20, "我的")]
    raw = {"width": 383, "height": 834, "listHash": "", "lines": [
        dict(x=x, y=y, w=w, h=14, conf=1.0, text=t, fg=[0, 0, 0], bg=[255, 255, 255]) for x, y, w, t in base + lines]}
    return scrape.Page(raw)

class SiteImagesTest(unittest.TestCase):
    def test_trim_square_centers_content(self):
        im = Image.new("RGB", (100, 100), "white")
        im.paste((200, 0, 0), (10, 30, 50, 50))          # 40 宽 20 高的红块
        out = site_images.trim_square(im)
        self.assertEqual(out.size, (40, 40))
        self.assertEqual(out.getpixel((20, 20)), (200, 0, 0))
        self.assertEqual(out.getpixel((20, 2)), (255, 255, 255))

    def test_trim_square_all_white(self):
        self.assertIsNone(site_images.trim_square(Image.new("RGB", (50, 50), "white")))

    def test_named_is_stable_and_content_based(self):
        self.assertEqual(site_images.named("a1", b"abc"), site_images.named("a1", b"abc"))
        self.assertNotEqual(site_images.named("a1", b"abc"), site_images.named("a1", b"abd"))
        self.assertRegex(site_images.named("a12", b"x"), r"^a12-[0-9a-f]{8}\.jpg$")

    def test_jd_versions_sizes(self):
        src = next((scrape.DATA / "jd_images").glob("*.jpg"))
        v = site_images.jd_versions(src)
        self.assertEqual(Image.open(io.BytesIO(v["t"])).size, (200, 200))
        self.assertEqual(Image.open(io.BytesIO(v["l"])).size, (600, 600))

    def test_head_score(self):
        n = scrape.norm
        self.assertEqual(site_images.head_score(n("光明 如实高蛋白希"), n("光明 如实高蛋白希腊发酵乳 135gx10")), 1.0)
        self.assertGreaterEqual(site_images.head_score(n("仅铁吧可售 MM 红油串串"), n("MM 红油串串")), 0.9)
        self.assertLess(site_images.head_score(n("东升 香菜125g"), n("洪湖粉藕 1kg")), 0.8)
        self.assertEqual(site_images.head_score("1k", n("1kg 鸡蛋")), 0.0)

    def test_locate_card_uses_price_below(self):
        page = fake_page([(188, 400, 120, "MM 澳洲牛排 1kg"), (189, 460, 40, "¥99"),
                          (188, 520, 120, "MM 澳洲牛排 2kg"), (189, 580, 40, "¥199")])
        self.assertEqual(site_images.locate_card(page, "MM 澳洲牛排 2kg", 199.0)["y"], 520)
        self.assertEqual(site_images.locate_card(page, "MM 澳洲牛排 1kg", 99.0)["y"], 400)

    def test_locate_card_ignores_spec_number_as_price(self):
        page = fake_page([(188, 400, 120, "植村秀琥珀卸妆油"), (187, 420, 40, "450ml"),
                          (188, 520, 120, "植村秀琥珀卸妆油"), (189, 580, 40, "¥450")])
        self.assertEqual(site_images.locate_card(page, "植村秀琥珀卸妆油450ml", 450.0)["y"], 520)

    def test_locate_card_ambiguous_without_price_returns_none(self):
        page = fake_page([(192, 400, 130, "全球购 BURBERRY博柏利 翻领"), (192, 520, 130, "全球购 BURBERRY博柏利 翻领")])
        self.assertIsNone(site_images.locate_card(page, "BURBERRY博柏利 翻领短袖POLO衫", 1999.0))

    def test_locate_card_image_must_be_fully_visible(self):
        top = fake_page([(188, 280, 120, "洪湖粉藕 1kg"), (189, 340, 40, "¥739")])        # 图上沿伸到表头里
        bottom = fake_page([(188, 720, 120, "洪湖粉藕 1kg"), (189, 750, 40, "¥739")])     # 图下沿伸到底部标签栏里
        self.assertIsNone(site_images.locate_card(top, "洪湖粉藕 1kg", 739.0))
        self.assertIsNone(site_images.locate_card(bottom, "洪湖粉藕 1kg", 739.0))

    def test_locate_card_same_price_siblings_use_second_line(self):
        """同一张截图里同系列又同价的两款，标题第一行一样，要拼上第二行再比（审查发现 ASKO 洗衣机配成了烘衣机的图）。"""
        page = fake_page([(190, 289, 120, "线上专享 ASKO 欧洲进口"), (187, 309, 120, "8kg极光系列烘衣机T108H"),
                          (190, 373, 50, "¥9,999"),
                          (188, 619, 120, "ASKO 欧洲进口9kg极光系"), (187, 639, 120, "列洗衣机W109C"),
                          (189, 703, 50, "¥9,999")])
        self.assertEqual(site_images.locate_card(page, "ASKO 欧洲进口9kg极光系列洗衣机W109C", 9999.0)["y"], 619)
        self.assertEqual(site_images.locate_card(page, "ASKO 欧洲进口8kg极光系列烘衣机T108H", 9999.0)["y"], 289)

    def test_locate_card_identical_siblings_returns_none(self):
        """拼上第二行还分不出来：不配图（占位图比别人的图好）。"""
        page = fake_page([(186, 412, 100, "BOLON 太阳镜"), (189, 472, 50, "¥499.9"),
                          (188, 629, 100, "BOLON 太阳镜"), (188, 688, 50, "¥499.9")])
        self.assertIsNone(site_images.locate_card(page, "BOLON 太阳镜", 499.9))

    def test_locate_card_real_siblings(self):
        """家电家居/00230.png 里 ASKO 烘衣机和洗衣机都是 ¥9,999，标题第一行一样。"""
        path = site_images.SHOTS / "家电家居" / "00230.png"
        page = scrape.Page(site_images.ocr_raw(path), path)
        self.assertEqual(site_images.locate_card(page, "ASKO 欧洲进口9kg极光系列洗衣机W109C", 9999.0)["y"], 619)

    def test_crop_for_cards_the_old_rules_missed(self):
        """这台笔记本（macOS 13）上按原解析规则找不到的真实商品：价格行太矮、标题横坐标差一点、
        标题前多了标签、图片上的字和标题并成一行、全球购卡上没识别出价格。"""
        cases = [("洪湖粉藕 1kg", 739.0, "肉蛋果蔬/00386.png"),
                 ("美都西瓜 1个", 49.8, "肉蛋果蔬/00434.png"),
                 ("MM 红油串串", 29.9, "速食冷冻/00035.png"),
                 ("五粮液2021年产小五粮 浓香型白酒52度 375mL", 219.9, "酒水饮料/00018.png"),
                 ("植村秀琥珀卸妆油450ml", 430.0, "个护美妆/00053.png")]
        for title, price, shot in cases:
            with self.subTest(title=title):
                data = site_images.crop_for({"members": [dict(title=title, price=price, shot=shot)]})
                self.assertIsNotNone(data)
                im = Image.open(io.BytesIO(data))
                self.assertEqual(im.size[0], im.size[1])

    def test_crop_for_product_not_in_shot(self):
        rec = dict(title="茅台 飞天 53度 500mL", price=1499.0, shot="肉蛋果蔬/00386.png")
        self.assertIsNone(site_images.crop_for({"members": [rec]}))

    def test_ocr_cache_follows_content(self):
        calls = []

        def fake(path):
            calls.append(path)
            return {"n": len(calls)}

        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(site_images, "SHOTS", Path(d) / "shots"), \
                mock.patch.object(site_images, "OCR_DIR", Path(d) / "ocr"), \
                mock.patch.object(scrape, "analyze_raw", fake):
            shot = Path(d) / "shots" / "酒水饮料" / "00001.png"
            shot.parent.mkdir(parents=True)
            shot.write_bytes(b"a")
            self.assertEqual(site_images.ocr_raw(shot), {"n": 1})
            self.assertEqual(site_images.ocr_raw(shot), {"n": 1})      # 内容没变：用缓存
            shot.write_bytes(b"b")
            self.assertEqual(site_images.ocr_raw(shot), {"n": 2})      # 内容变了（重新抓过）：重新识别
            self.assertEqual(len(calls), 2)

    def test_crop_for_real_product(self):
        """洋河海之蓝（items.jsonl 第 993 条）在 酒水饮料/00008.png 里。裁出来的应是方图，宽在 60～130 像素之间。"""
        rec = dict(id=993, top="酒水饮料", sub="白酒", title="洋河52度 海之蓝 1L", price=269.9, shot="酒水饮料/00008.png")
        data = site_images.crop_for({"members": [rec]})
        self.assertIsNotNone(data)
        im = Image.open(io.BytesIO(data))
        self.assertEqual(im.size[0], im.size[1])
        self.assertTrue(60 <= im.size[0] <= 130, im.size)


if __name__ == "__main__":
    unittest.main()
