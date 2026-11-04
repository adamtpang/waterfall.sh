from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "router"))

import license as lic  # noqa: E402


class LicenseTests(unittest.TestCase):
    def test_paid_writes_file(self):
        tmp = Path(tempfile.mkdtemp()) / "license.json"
        with mock.patch.object(lic, "LICENSE_PATH", tmp):
            out = lic.mark_paid()
        self.assertTrue(out["ok"])
        self.assertEqual(out["kind"], "paid")
        body = json.loads(tmp.read_text(encoding="utf-8"))
        self.assertEqual(body["price_usd"], 30)

    def test_missing_is_not_ok_when_not_founder(self):
        tmp = Path(tempfile.mkdtemp()) / "missing.json"
        with mock.patch.object(lic, "LICENSE_PATH", tmp):
            with mock.patch.object(lic, "is_founder_machine", return_value=False):
                out = lic.status()
        self.assertFalse(out["ok"])
        self.assertEqual(out["kind"], "none")


if __name__ == "__main__":
    unittest.main()
