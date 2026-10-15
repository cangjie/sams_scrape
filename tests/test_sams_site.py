import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import sams_site  # noqa: E402


class SamsSiteTest(unittest.TestCase):
    def test_render_index_replaces_placeholders(self):
        html = sams_site.render_index('<link href="{{CSS}}"><body data-src="{{DATA}}"><script src="{{JS}}">',
                                      "app.1.css", "app.2.js", "data/products.3.json")
        self.assertEqual(html, '<link href="app.1.css"><body data-src="data/products.3.json"><script src="app.2.js">')

    def test_render_index_rejects_missing_placeholder(self):
        with self.assertRaises(ValueError):
            sams_site.render_index("<html></html>", "a.css", "a.js", "d.json")

    def test_real_template_has_placeholders(self):
        html = sams_site.render_index((ROOT / "site" / "index.html").read_text(encoding="utf-8"), "c", "j", "d")
        self.assertNotIn("{{", html)

    def test_same_image_groups(self):
        images = {"a1": ("img/t/a1-aaaa1111.jpg", "img/l/a1-aaaa1111.jpg"),
                  "a2": ("img/t/a2-aaaa1111.jpg", "img/t/a2-aaaa1111.jpg"),
                  "a3": ("img/t/a3-bbbb2222.jpg", "img/t/a3-bbbb2222.jpg")}
        self.assertEqual(sams_site.same_image_groups(images), [["a1", "a2"]])

    def test_jd_picks_one_app_product_per_jd_item(self):
        """一个京东商品只给名字最像的 App 商品用主图（「MM 进口椰子水」和「三麟 进口 椰子水」配上了同一个京东商品）；
        一个 App 商品配上几个京东商品时取最像的。"""
        pairs = [(0, 5, 0.9), (1, 5, 0.7), (1, 6, 0.8), (2, 7, 0.95), (2, 8, 0.6), (3, 5, 0.85)]
        self.assertEqual(sams_site.jd_picks(pairs), {0: 5, 1: 6, 2: 7})

    def test_stage_gzips_json_only(self):
        import gzip
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            src, dst = Path(d) / "dist", Path(d) / "stage"
            (src / "data").mkdir(parents=True)
            (src / "data" / "products.abc.json").write_bytes(b'{"a":1}')
            (src / "index.html").write_bytes(b"<html>")
            sams_site.stage(src, dst)
            self.assertEqual(gzip.decompress((dst / "data" / "products.abc.json").read_bytes()), b'{"a":1}')
            self.assertEqual((dst / "index.html").read_bytes(), b"<html>")
            self.assertEqual((src / "data" / "products.abc.json").read_bytes(), b'{"a":1}')   # dist/ 本身不动


if __name__ == "__main__":
    unittest.main()
