import datetime as dt
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKSHOP = ROOT / "workshop"


class WorkshopCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((WORKSHOP / "catalog.json").read_text(encoding="utf-8"))

    def test_catalog_has_expected_collections(self):
        collections = {collection["id"]: collection for collection in self.catalog["collections"]}
        self.assertEqual({"models", "ides", "skills", "mcps"}, set(collections))
        for collection in collections.values():
            self.assertGreaterEqual(len(collection["items"]), 6)

    def test_catalog_items_have_sources_negative_cases_and_dates(self):
        required = {
            "id",
            "name",
            "publisher",
            "url",
            "role",
            "default_state",
            "evidence",
            "avoid",
            "access",
            "tags",
            "checked_at",
            "source_date",
            "volatility",
            "refresh_cadence",
        }
        ids = []
        for collection in self.catalog["collections"]:
            for item in collection["items"]:
                self.assertFalse(required - set(item), f"{item.get('id')} is missing fields")
                self.assertTrue(item["url"].startswith(("https://", "./")))
                self.assertTrue(item["avoid"].strip())
                self.assertTrue(item["tags"])
                dt.date.fromisoformat(item["checked_at"])
                dt.date.fromisoformat(item["source_date"])
                ids.append(item["id"])
        self.assertEqual(len(ids), len(set(ids)), "catalog IDs must be unique")

    def test_public_workshop_has_no_private_machine_markers(self):
        forbidden = (
            r"C:\\Users\\",
            r"/Users/",
            r"\.claude/",
            r"\.codex/",
            r"OPENROUTER_API_KEY",
            r"ANTHROPIC_API_KEY",
            r"BROWSER_USE_API_KEY",
            r"sk-[A-Za-z0-9]",
        )
        public_files = [path for path in WORKSHOP.rglob("*") if path.is_file()]
        for path in public_files:
            text = path.read_text(encoding="utf-8")
            for pattern in forbidden:
                self.assertIsNone(re.search(pattern, text), f"{path} contains {pattern}")

    def test_public_workshop_uses_no_em_dashes(self):
        for path in WORKSHOP.rglob("*"):
            if path.is_file():
                self.assertNotIn("—", path.read_text(encoding="utf-8"), str(path))

    def test_starter_skills_have_valid_frontmatter_names(self):
        expected = {"next", "research-report", "waterfall"}
        actual = set()
        for skill_path in (WORKSHOP / "skills").glob("*/SKILL.md"):
            text = skill_path.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\n"))
            match = re.search(r"^name:\s*([^\n]+)$", text, re.MULTILINE)
            self.assertIsNotNone(match, str(skill_path))
            actual.add(match.group(1).strip())
        self.assertEqual(expected, actual)

    def test_static_site_links_to_workshop_assets(self):
        workshop_html = (WORKSHOP / "index.html").read_text(encoding="utf-8")
        root_html = (ROOT / "index.html").read_text(encoding="utf-8")
        sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
        llms = (ROOT / "llms.txt").read_text(encoding="utf-8")
        self.assertIn("fetch('./catalog.json')", workshop_html)
        self.assertIn('data-filter="models"', workshop_html)
        self.assertIn('href="/workshop/"', root_html)
        self.assertIn("https://waterfall.sh/workshop/", sitemap)
        self.assertIn("workshop/catalog.json", llms)


if __name__ == "__main__":
    unittest.main()
