import json
import tempfile
import unittest
from pathlib import Path

from diagnostico import analysis, app, report

DEMO = json.loads((Path(__file__).parent.parent / "diagnostico" / "demo.json").read_text(encoding="utf-8"))


class Report(unittest.TestCase):
    def test_render_escapes_user_text(self):
        html = report.render(DEMO, analysis.analyse(DEMO), "INC1", "<script>alert(1)</script>")
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert(1)</script>", html)

    def test_render_without_data(self):
        html = report.render({"system": {"computer": "PC"}}, [])
        self.assertIn("No se han encontrado problemas", html)
        self.assertIn("No hay impresoras instaladas", html)

    def test_run_demo_writes_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            html, findings, summary = app.run(ticket="INC 77/1", folder=tmp, demo=True, save_json=True)
            self.assertTrue(html.exists())
            self.assertTrue(html.with_suffix(".json").exists())
            self.assertIn("INC-77-1", html.name)
            self.assertTrue(findings)
            self.assertIn("PC-OFICINA-07", summary)


if __name__ == "__main__":
    unittest.main()
