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

    def test_find_card_fuzzy_same_price(self):
        cards = [dict(title="洋河 52度 海之蓝儿", price=269.9, y=461), dict(title="汾酒 青花20", price=419.9, y=557)]
        self.assertEqual(site_images.find_card(cards, "洋河52度 海之蓝 1L", 269.9)["y"], 461)
        self.assertIsNone(site_images.find_card(cards, "洋河52度 海之蓝 1L", 239.9))
        self.assertIsNone(site_images.find_card(cards, "茅台飞天", 269.9))

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
