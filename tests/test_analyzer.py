import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scrape  # noqa: E402

SHOT = scrape.DATA / "shots" / "酒水饮料" / "00008.png"     # 洋河 52 度海之蓝 ¥269.9 在这张截图里


class AnalyzerTest(unittest.TestCase):
    def test_raw_result(self):
        raw = scrape.analyze_raw(SHOT)
        self.assertIsNotNone(raw, "识别程序在本机跑不起来")
        self.assertIn("lines", raw)
        self.assertEqual((raw["width"], raw["height"]), (452, 983))

    def test_reads_price_from_screenshot(self):
        page = scrape.analyze(SHOT)
        self.assertIsNotNone(page, "识别程序在本机跑不起来")
        texts = [l["text"] for l in page.lines]
        self.assertTrue(any("269.9" in t for t in texts), texts)

    def test_cards_parsed(self):
        cards = scrape.parse_cards(scrape.analyze(SHOT), strict=False)
        self.assertIn(269.9, [c["price"] for c in cards])


if __name__ == "__main__":
    unittest.main()
