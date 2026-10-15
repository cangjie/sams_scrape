import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy"))

import nginx_sams  # noqa: E402

CONF = """server {
    listen 443 ssl;
    server_name mini.snowmeet.top;
    location / {
        proxy_pass http://localhost:5000;
    }
}
"""
ANCHOR = "location / {"


class NginxSamsTest(unittest.TestCase):
    def test_add_inserts_before_anchor_with_same_indent(self):
        out = nginx_sams.add(CONF, ANCHOR, "127.0.0.53")
        self.assertIn("    location = /sams { return 301 /sams/; }\n", out)
        self.assertIn("    location ^~ /sams/ {\n        resolver 127.0.0.53 valid=300s ipv6=off;\n", out)
        self.assertIn("        proxy_pass https://$sams_origin;\n", out)
        self.assertLess(out.index("location = /sams"), out.index(ANCHOR))
        self.assertTrue(out.endswith(CONF[CONF.index("    " + ANCHOR):]))

    def test_add_refuses_ambiguous_anchor(self):
        with self.assertRaises(SystemExit):
            nginx_sams.add(CONF + CONF, ANCHOR, "127.0.0.53")

    def test_add_refuses_twice(self):
        once = nginx_sams.add(CONF, ANCHOR, "127.0.0.53")
        with self.assertRaises(SystemExit):
            nginx_sams.add(once, ANCHOR, "127.0.0.53")

    def test_remove_restores_original(self):
        self.assertEqual(nginx_sams.remove(nginx_sams.add(CONF, ANCHOR, "127.0.0.53")), CONF)

    def test_remove_without_rules_refuses(self):
        with self.assertRaises(SystemExit):
            nginx_sams.remove(CONF)


if __name__ == "__main__":
    unittest.main()
