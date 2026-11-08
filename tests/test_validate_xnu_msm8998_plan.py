import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("plan_validator", ROOT / "tools" / "validate_xnu_msm8998_plan.py")
MOD = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MOD)
BASE = json.loads((ROOT / "config" / "xnu-msm8998-port-plan.json").read_text())
PLATFORM = json.loads((ROOT / "config" / "msm8998-platform.json").read_text())


class PortPlanValidatorTests(unittest.TestCase):
    def check(self, mutate=None):
        value = copy.deepcopy(BASE)
        if mutate: mutate(value)
        return MOD.validate(value, PLATFORM)

    def test_reference_plan(self): self.assertEqual(self.check(), [])

    def test_rejects_readiness_claim(self):
        errors = self.check(lambda d: d.__setitem__("boot_readiness_claimed", True))
        self.assertTrue(any("must remain false" in e for e in errors))

    def test_rejects_milestone_sha_change(self):
        errors = self.check(lambda d: d["integration"].__setitem__("phase_2b_commit", "0" * 40))
        self.assertTrue(any("milestone SHA mismatch" in e for e in errors))

    def test_rejects_uninspected_source_path(self):
        errors = self.check(lambda d: d["source_map"][0].__setitem__("source_path", "invented/path.c"))
        self.assertTrue(any("not directly inspected" in e for e in errors))

    def test_unresolved_mapping_cannot_invent_symbol(self):
        def mutate(d):
            item = next(x for x in d["source_map"] if x["inspection"] == "unresolved-mapping")
            item["source_path"] = "osfmk/fake.c"; item["symbols"] = ["fake"]
        self.assertTrue(any("must not invent" in e for e in self.check(mutate)))

    def test_hardware_claim_requires_phase2b_provenance(self):
        errors = self.check(lambda d: d["hardware_claims"][0].__setitem__("provenance", "trust me"))
        self.assertTrue(any("Phase 2B provenance" in e for e in errors))

    def test_hardware_value_must_match_phase2b_descriptor(self):
        errors = self.check(lambda d: d["hardware_claims"][0].__setitem__("value", 99))
        self.assertTrue(any("differs from Phase 2B" in e for e in errors))

    def test_rejects_initialization_reordering(self):
        def mutate(d): d["initialization_sequence"][0], d["initialization_sequence"][1] = d["initialization_sequence"][1], d["initialization_sequence"][0]
        self.assertTrue(any("stage IDs/order" in e for e in self.check(mutate)))

    def test_stage_requires_failure_conditions(self):
        errors = self.check(lambda d: d["initialization_sequence"][0].__setitem__("failure_conditions", []))
        self.assertTrue(any("failure_conditions" in e for e in errors))

    def test_rejects_unknown_compatibility_category(self):
        errors = self.check(lambda d: d["compatibility"][0].__setitem__("category", "probably"))
        self.assertTrue(any("category: unsupported" in e for e in errors))

    def test_milestone_requires_offline_tests(self):
        errors = self.check(lambda d: d["roadmap"][0].__setitem__("offline_tests", []))
        self.assertTrue(any("offline_tests" in e for e in errors))
