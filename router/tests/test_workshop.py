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
        cls.packs = json.loads((WORKSHOP / "packs.json").read_text(encoding="utf-8"))

    def test_catalog_has_expected_collections(self):
        collections = {collection["id"]: collection for collection in self.catalog["collections"]}
        self.assertEqual({"models", "ides", "skills", "mcps"}, set(collections))
        for collection in collections.values():
            self.assertGreaterEqual(len(collection["items"]), 6)

    def test_catalog_metadata_and_collection_schema(self):
        self.assertEqual(2, self.catalog["schema_version"])
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
            "ranking_eligible",
            "rank",
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
                self.assertIsInstance(item["ranking_eligible"], bool)
                if item["ranking_eligible"]:
                    self.assertIsInstance(item["rank"], int)
                    self.assertGreater(item["rank"], 0)
                else:
                    self.assertIsNone(item["rank"])
                dt.date.fromisoformat(item["checked_at"])
                dt.date.fromisoformat(item["source_date"])
                ids.append(item["id"])
        self.assertEqual(len(ids), len(set(ids)), "catalog IDs must be unique")

    def test_rankings_are_dated_scoped_and_contiguous(self):
        ranking = self.catalog["ranking"]
        dt.date.fromisoformat(ranking["as_of"])
        self.assertIn("Waterfall fit", ranking["scope"])
        self.assertEqual("weekly", ranking["refresh_cadence"])
        self.assertGreaterEqual(len(ranking["methodology"]), 4)
        signals = {signal["name"]: signal for signal in ranking["signals"]}
        self.assertEqual({"Agent Arena", "skills.sh", "MCP Registry", "mcp.directory"}, set(signals))
        self.assertIn("not task performance", signals["skills.sh"]["limit"])
        self.assertIn("No public ranking methodology", signals["mcp.directory"]["limit"])

        for collection in self.catalog["collections"]:
            ranks = sorted(item["rank"] for item in collection["items"] if item["ranking_eligible"])
            self.assertEqual(list(range(1, len(ranks) + 1)), ranks, collection["id"])

    def test_starter_pack_schema_and_catalog_references(self):
        self.assertEqual(1, self.packs["schema_version"])
        dt.date.fromisoformat(self.packs["updated_at"])
        self.assertEqual(6, len(self.packs["archetypes"]))
        self.assertEqual(4, len(self.packs["quiz"]))
        self.assertGreaterEqual(len(self.packs["safety"]), 5)
        catalog_ids = {
            item["id"]
            for collection in self.catalog["collections"]
            for item in collection["items"]
        }
        archetype_ids = []
        for archetype in self.packs["archetypes"]:
            self.assertTrue({
                "id", "name", "sigil", "tagline", "description", "best_for",
                "permission_posture", "catalog_ids",
            } <= set(archetype))
            self.assertTrue(archetype["catalog_ids"])
            self.assertFalse(set(archetype["catalog_ids"]) - catalog_ids, archetype["id"])
            self.assertEqual(len(archetype["catalog_ids"]), len(set(archetype["catalog_ids"])))
            archetype_ids.append(archetype["id"])
        self.assertEqual(len(archetype_ids), len(set(archetype_ids)))

        for question in self.packs["quiz"]:
            self.assertEqual(3, len(question["options"]))
            for option in question["options"]:
                self.assertTrue(option["scores"])
                self.assertFalse(set(option["scores"]) - set(archetype_ids))
                self.assertTrue(all(isinstance(points, int) and points > 0 for points in option["scores"].values()))

    def test_public_workshop_has_no_private_machine_markers(self):
        forbidden = (
            r"C:\\Users\\",
            r"/Users/",
            r"\.claude/",
            r"\.codex/",
            r"OPENROUTER_API_KEY",
            r"ANTHROPIC_API_KEY",
            r"BROWSER_USE_API_KEY",
            r"(?<![A-Za-z0-9])sk-[A-Za-z0-9]{8,}",
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
        packs_html = (WORKSHOP / "starter-packs.html").read_text(encoding="utf-8")
        packs_js = (WORKSHOP / "starter-packs.js").read_text(encoding="utf-8")
        root_html = (ROOT / "index.html").read_text(encoding="utf-8")
        sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
        llms = (ROOT / "llms.txt").read_text(encoding="utf-8")
        self.assertIn('src="/workshop/workshop.js"', workshop_html)
        self.assertIn('href="/workshop/workshop.css"', workshop_html)
        self.assertIn("fetch('/workshop/catalog.json')", workshop_js)
        self.assertIn('src="/workshop/starter-packs.js"', packs_html)
        self.assertIn('href="/workshop/starter-packs.css"', packs_html)
        self.assertIn("fetch('/workshop/packs.json')", packs_js)
        self.assertIn("fetch('/workshop/catalog.json')", packs_js)
        self.assertIn('data-filter="models"', workshop_html)
        self.assertIn('href="/workshop/"', root_html)
        self.assertIn("https://waterfall.sh/workshop/", sitemap)
        self.assertIn("https://waterfall.sh/workshop/starter-packs", sitemap)
        self.assertIn("workshop/catalog.json", llms)
        self.assertIn("workshop/packs.json", llms)
        self.assertIn('href="/workshop/starter-packs"', root_html)

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
        starter_html = (WORKSHOP / "starter-packs.html").read_text(encoding="utf-8")
        vercel = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        csp = next(
            header["value"]
            for rule in vercel["headers"]
            for header in rule["headers"]
            if header["key"] == "Content-Security-Policy"
        )
        self.assertIn("script-src 'self'", csp)
        self.assertIn("style-src 'self'", csp)
        for page in (workshop_html, starter_html):
            self.assertNotIn("<style", page)
            self.assertIsNone(re.search(r"<script(?![^>]+\bsrc=)", page))
            self.assertIsNone(re.search(r"\sstyle=", page))

        ignore_rules = {
            line.strip()
            for line in (ROOT / ".vercelignore").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }
        self.assertNotIn("*.md", ignore_rules, "recursive Markdown ignore hides workshop resources")
        self.assertIn("/*.md", ignore_rules, "root handoff Markdown should remain excluded")
        for resource in ("README.md", "AUDIT.md", "catalog.json", "packs.json"):
            self.assertTrue((WORKSHOP / resource).is_file())


if __name__ == "__main__":
    unittest.main()
