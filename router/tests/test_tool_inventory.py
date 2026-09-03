import tempfile
import unittest
from pathlib import Path

from router.tool_inventory import (
    discover_codex_plugins,
    discover_mcp_servers,
    discover_skills,
    render_markdown,
)


SKILL = """---
name: {name}
description: fixture
---
"""


class ToolInventoryTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.home = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def _write(self, relative: str, text: str):
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_skill_discovery_excludes_backups_and_nested_claude_repositories(self):
        self._write(".agents/skills/alpha/SKILL.md", SKILL.format(name="alpha"))
        self._write(".agents/skills/.backups/old/SKILL.md", SKILL.format(name="old"))
        self._write(".codex/skills/shared/SKILL.md", SKILL.format(name="shared"))
        self._write(".claude/skills/shared/SKILL.md", SKILL.format(name="shared") + "Claude copy\n")
        self._write(".claude/skills/repo/internal/SKILL.md", SKILL.format(name="internal"))
        self._write(".codex/plugins/cache/vendor/pkg/1/skills/plugin/SKILL.md", SKILL.format(name="plugin"))

        records = discover_skills(self.home)
        self.assertEqual({"alpha", "shared", "plugin"}, {record.name for record in records})
        self.assertEqual(2, sum(record.name == "shared" for record in records))

    def test_mcp_discovery_reports_names_and_status_without_secret_values(self):
        self._write(
            ".codex/config.toml",
            '[mcp_servers.docs]\nenabled = true\nurl = "https://example.test"\n'
            '[mcp_servers.dormant]\nenabled = false\nenv = { API_KEY = "never-leak" }\n',
        )
        self._write(
            ".claude.json",
            '{"mcpServers":{"github":{"env":{"TOKEN":"never-leak"}}},'
            '"projects":{"private-path":{"mcpServers":{"docs":{"enabled":true},'
            '"C:\\\\Users\\\\private\\\\server":{"enabled":true}}}}}',
        )

        records = discover_mcp_servers(self.home)
        report = render_markdown([], records, [], checked_at="2026-09-03")

        self.assertEqual(
            {"docs", "dormant", "github", r"C:\Users\private\server"},
            {record.name for record in records},
        )
        self.assertIn("| dormant | Codex | no | 1 |", report)
        self.assertIn("| [redacted unsafe name] | Claude | yes | 1 |", report)
        self.assertNotIn("never-leak", report)
        self.assertNotIn("private-path", report)
        self.assertNotIn(r"C:\Users\private\server", report)
        self.assertNotIn("https://example.test", report)

    def test_render_marks_divergent_skill_copies_and_lists_plugins(self):
        self._write(".agents/skills/shared/SKILL.md", SKILL.format(name="shared"))
        self._write(".claude/skills/shared/SKILL.md", SKILL.format(name="shared") + "different\n")
        self._write(
            ".codex/plugins/cache/openai-curated-remote/notion/.codex-remote-plugin-install.json",
            "{}",
        )

        skills = discover_skills(self.home)
        plugins = discover_codex_plugins(self.home)
        report = render_markdown(skills, [], plugins, checked_at="2026-09-03")

        self.assertIn("Duplicated names with different contents: 1", report)
        self.assertIn("| shared | Claude skills, shared agent skills | 2 | yes |", report)
        self.assertIn("- notion", report)
        self.assertNotIn(str(self.home), report)


if __name__ == "__main__":
    unittest.main()
