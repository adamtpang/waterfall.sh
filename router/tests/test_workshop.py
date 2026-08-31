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

    def test_catalog_metadata_and_collection_schema(self):
        self.assertEqual(1, self.catalog["schema_version"])
        self.assertEqual("Waterfall Workshop", self.catalog["title"])
        dt.date.fromisoformat(self.catalog["updated_at"])
        self.assertTrue(self.catalog["summary"].strip())
        self.assertGreaterEqual(len(self.catalog["principles"]), 4)
        self.assertEqual(
            {"active_skills", "unused_skills_removed", "public_starter_skills", "affiliate_links"},
            set(self.catalog["audit"]),
        )
        for value in self.catalog["audit"].values():
            self.assertIsInstance(value, int)
            self.assertGreaterEqual(value, 0)

        required = {"id", "title", "summary", "items"}
        for collection in self.catalog["collections"]:
            self.assertFalse(required - set(collection), collection.get("id"))
            self.assertTrue(collection["title"].strip())
            self.assertTrue(collection["summary"].strip())

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
        allowed_states = {"hard-work", "daily", "routine", "optional", "pilot", "reference"}
        allowed_volatility = {"live", "daily", "high", "medium", "low"}
        allowed_refresh = {"live", "weekly", "monthly", "quarterly"}
        for collection in self.catalog["collections"]:
            for item in collection["items"]:
                self.assertFalse(required - set(item), f"{item.get('id')} is missing fields")
                self.assertTrue(item["url"].startswith(("https://", "/workshop/")))
                self.assertTrue(item["avoid"].strip())
                self.assertIsInstance(item["tags"], list)
                self.assertTrue(item["tags"])
                self.assertTrue(all(isinstance(tag, str) and tag.strip() for tag in item["tags"]))
                self.assertIn(item["default_state"], allowed_states)
                self.assertIn(item["volatility"], allowed_volatility)
                self.assertIn(item["refresh_cadence"], allowed_refresh)
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

    def test_local_catalog_urls_resolve_to_public_files(self):
        for collection in self.catalog["collections"]:
            for item in collection["items"]:
                url = item["url"]
                if url.startswith("/workshop/"):
                    target = ROOT / url.removeprefix("/")
                    self.assertTrue(target.is_file(), f"{item['id']} points to missing {target}")

    def test_static_site_links_to_workshop_assets(self):
        workshop_html = (WORKSHOP / "index.html").read_text(encoding="utf-8")
        workshop_js = (WORKSHOP / "workshop.js").read_text(encoding="utf-8")
        root_html = (ROOT / "index.html").read_text(encoding="utf-8")
        sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
        llms = (ROOT / "llms.txt").read_text(encoding="utf-8")
        self.assertIn('src="/workshop/workshop.js"', workshop_html)
        self.assertIn('href="/workshop/workshop.css"', workshop_html)
        self.assertIn("fetch('/workshop/catalog.json')", workshop_js)
        self.assertIn('data-filter="models"', workshop_html)
        self.assertIn('href="/workshop/"', root_html)
        self.assertIn("https://waterfall.sh/workshop/", sitemap)
        self.assertIn("workshop/catalog.json", llms)

    def test_visible_snapshot_uses_catalog_metadata(self):
        workshop_html = (WORKSHOP / "index.html").read_text(encoding="utf-8")
        workshop_js = (WORKSHOP / "workshop.js").read_text(encoding="utf-8")
        for snapshot_id in (
            "snapshot-checked",
            "snapshot-active",
            "snapshot-removed",
            "snapshot-public",
            "snapshot-affiliate",
        ):
            self.assertIn(f'id="{snapshot_id}"', workshop_html)
            self.assertIn(f"'{snapshot_id}'", workshop_js)
        public_skills = sum(
            item["publisher"] == "Waterfall Workshop"
            for collection in self.catalog["collections"]
            for item in collection["items"]
        )
        self.assertEqual(self.catalog["audit"]["public_starter_skills"], public_skills)

    def test_static_site_has_no_javascript_and_load_failure_fallbacks(self):
        workshop_html = (WORKSHOP / "index.html").read_text(encoding="utf-8")
        workshop_js = (WORKSHOP / "workshop.js").read_text(encoding="utf-8")
        self.assertIn("<noscript>", workshop_html)
        self.assertIn('href="/workshop/catalog.json"', workshop_html)
        self.assertIn('href="/workshop/README.md"', workshop_html)
        self.assertIn("interactive catalog could not load", workshop_js)

    def test_workshop_assets_match_the_deployment_contract(self):
        workshop_html = (WORKSHOP / "index.html").read_text(encoding="utf-8")
        vercel = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        csp = next(
            header["value"]
            for rule in vercel["headers"]
            for header in rule["headers"]
            if header["key"] == "Content-Security-Policy"
        )
        self.assertIn("script-src 'self'", csp)
        self.assertIn("style-src 'self'", csp)
        self.assertNotIn("<style", workshop_html)
        self.assertIsNone(re.search(r"<script(?![^>]+\bsrc=)", workshop_html))
        self.assertIsNone(re.search(r"\sstyle=", workshop_html))

        ignore_rules = {
            line.strip()
            for line in (ROOT / ".vercelignore").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }
        self.assertNotIn("*.md", ignore_rules, "recursive Markdown ignore hides workshop resources")
        self.assertIn("/*.md", ignore_rules, "root handoff Markdown should remain excluded")
        for resource in ("README.md", "AUDIT.md"):
            self.assertTrue((WORKSHOP / resource).is_file())


if __name__ == "__main__":
    unittest.main()
