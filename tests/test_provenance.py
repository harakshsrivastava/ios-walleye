import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "evidence" / "provenance.json"


class ProvenanceTests(unittest.TestCase):
    def test_manifest_is_valid_json(self):
        data = json.loads(MANIFEST.read_text())
        self.assertEqual(data["schema_version"], 1)

    def test_pinned_commits_are_full_sha1(self):
        data = json.loads(MANIFEST.read_text())
        for value in data["source_baselines"].values():
            self.assertEqual(len(value["commit"]), 40)
            int(value["commit"], 16)

    def test_historical_claims_are_labeled(self):
        data = json.loads(MANIFEST.read_text())
        self.assertIs(data["historical_recovery_record"]["revalidated"], False)

    def test_no_raw_device_artifacts_tracked(self):
        forbidden = {".dtb", ".img", ".bin"}
        found = [p for p in ROOT.rglob("*") if p.is_file() and p.suffix in forbidden]
        self.assertEqual(found, [])
