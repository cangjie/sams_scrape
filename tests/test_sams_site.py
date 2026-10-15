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


if __name__ == "__main__":
    unittest.main()
