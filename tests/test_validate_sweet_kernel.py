import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("validator", Path(__file__).parents[1] / "tools" / "validate_sweet_kernel.py")
MOD = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MOD)


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.report = {"sha256":"a", "size":1, "header":{"architecture":"arm64", "filetype_name":"MH_EXECUTE"},
                       "entry":{"kind":"LC_UNIXTHREAD", "nearest_symbol":"__start"},
                       "fixups":[], "relocations":{"section_total":0,"external":0,"local":2}}
        self.reference = {"kernel":{"sha256":"a", "size_bytes":1, "architecture":"arm64", "filetype":"MH_EXECUTE",
                          "entry_kind":"LC_UNIXTHREAD", "entry_symbol":"__start", "dyld_fixups":[],
                          "relocations":{"section_total":0,"external":0,"local":2}}}

    def test_match(self): self.assertEqual(MOD.validate(self.report, self.reference), [])
    def test_hash_mismatch(self):
        self.report["sha256"] = "bad"
        self.assertIn("sha256", MOD.validate(self.report, self.reference)[0])
    def test_relocation_mismatch(self):
        self.report["relocations"]["local"] = 3
        self.assertIn("relocations", MOD.validate(self.report, self.reference)[0])
