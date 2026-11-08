import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


MODULE = load_module("walleye_adt_validator", ROOT / "tools" / "validate_walleye_adt.py")
M3A = load_module(
    "walleye_platform_expert_validator",
    ROOT / "tools" / "validate_walleye_platform_expert.py",
)
POLICY = json.loads((ROOT / "config" / "walleye-adt-policy.json").read_text())
BASE = json.loads((ROOT / "fixtures" / "adt" / "minimal-structural.json").read_text())


class WalleyeAdtValidatorTests(unittest.TestCase):
    def check(self, mutate=None, policy_mutate=None, raw_size=None):
        fixture = copy.deepcopy(BASE)
        policy = copy.deepcopy(POLICY)
        if mutate:
            mutate(fixture)
        if policy_mutate:
            policy_mutate(policy)
        return MODULE.validate_fixture(fixture, policy, ROOT, raw_size)

    def assert_invalid(self, mutate=None, policy_mutate=None, raw_size=None):
        status, errors, _ = self.check(mutate, policy_mutate, raw_size)
        self.assertEqual(status, "invalid")
        self.assertTrue(errors)

    def test_minimal_structural_fixture(self):
        status, errors, unresolved = self.check()
        self.assertEqual(status, "valid_with_unresolved")
        self.assertEqual(errors, [])
        self.assertEqual(len(unresolved), 42)

    def test_root_only_structural_fixture(self):
        status, errors, _ = self.check(lambda data: data["tree"].__setitem__("children", []))
        self.assertEqual(status, "valid_with_unresolved")
        self.assertEqual(errors, [])

    def test_checked_negative_fixtures_are_invalid(self):
        for path in sorted((ROOT / "fixtures" / "adt").glob("invalid-*.json")):
            if path.name == "invalid-duplicate-json-key.json":
                continue
            with self.subTest(path=path.name):
                fixture, size = MODULE.load_json(path)
                status, errors, _ = MODULE.validate_fixture(fixture, POLICY, ROOT, size)
                self.assertEqual(status, "invalid")
                self.assertTrue(errors)

    def test_incorrect_physical_identity(self):
        self.assert_invalid(
            lambda data: data["identity"]["physical_board"].__setitem__("codename", "taimen")
        )

    def test_sweet_identity_injection(self):
        self.assert_invalid(
            lambda data: data["identity"]["physical_board"].__setitem__("product", "Xiaomi SWEET")
        )

    def test_conflicting_adt_identity(self):
        def mutate(data):
            data["identity"]["adt_root"].update({
                "status": "verified",
                "match_property": "compatible",
                "match_value": "google,walleye",
            })
        self.assert_invalid(mutate)

    def test_missing_property_provenance(self):
        self.assert_invalid(
            lambda data: data["tree"]["properties"][0].__setitem__("provenance", "")
        )

    def test_unsupported_fixture_policy_version(self):
        self.assert_invalid(lambda data: data.__setitem__("policy_version", 2))

    def test_policy_bounds_cannot_expand_without_revision(self):
        self.assert_invalid(
            policy_mutate=lambda policy: policy["limits"].__setitem__("maximum_node_count", 3)
        )

    def test_unknown_node(self):
        def mutate(data):
            data["tree"]["children"][0]["path"] = "/mystery"
        self.assert_invalid(mutate)

    def test_duplicate_node_path(self):
        def mutate(data):
            data["tree"]["children"].append(copy.deepcopy(data["tree"]["children"][0]))
        self.assert_invalid(mutate)

    def test_duplicate_property(self):
        def mutate(data):
            data["tree"]["properties"].append(copy.deepcopy(data["tree"]["properties"][0]))
        self.assert_invalid(mutate)

    def test_excessive_tree_depth(self):
        def mutate(data):
            data["tree"]["children"][0]["children"].append({
                "path": "/chosen/extra",
                "node_type": "structural",
                "properties": [],
                "children": [],
            })
        self.assert_invalid(mutate)

    def test_oversized_property(self):
        self.assert_invalid(
            lambda data: data["tree"]["properties"][0].__setitem__("value", "x" * 65)
        )

    def test_invalid_property_type(self):
        self.assert_invalid(
            lambda data: data["tree"]["properties"][0].__setitem__("type", "uint32")
        )

    def test_unsupported_hardware_node(self):
        def mutate(data):
            data["tree"]["children"][0]["path"] = "/arm-io"
            data["tree"]["children"][0]["node_type"] = "hardware"
        self.assert_invalid(mutate)

    def test_runtime_enablement_rejected(self):
        self.assert_invalid(
            lambda data: data["runtime"].__setitem__("iokit_node_publication_enabled", True)
        )

    def test_m2_and_m3a_consistency(self):
        errors, unresolved = MODULE.project_consistency(POLICY, ROOT)
        self.assertEqual(errors, [])
        self.assertEqual(len(unresolved), 38)
        expert = json.loads((ROOT / "config" / "walleye-platform-expert.json").read_text())
        self.assertFalse(expert["source_integration"]["runtime_match_enabled"])
        self.assertFalse(expert["behavior"]["start_supported"])
        self.assertEqual(expert["behavior"]["adt_node_publication"], "none")
        patch = (ROOT / "patches" / "xnu" / "0002-walleye-platform-expert.patch").read_text()
        source = M3A.added_file_from_patch(patch, "iokit/Kernel/arm/WalleyePlatformExpert.cpp")
        self.assertIn("WalleyePlatformExpert::start", source)
        self.assertIn("return false;", source)
        self.assertNotIn("createNubs", source)

    def test_m2_count_inconsistency_rejected(self):
        self.assert_invalid(
            policy_mutate=lambda policy: policy["project_dependencies"].__setitem__(
                "m2_required_unresolved_count", 37
            )
        )

    def test_malformed_tree_structure(self):
        self.assert_invalid(lambda data: data["tree"].__setitem__("children", {}))

    def test_unresolved_root_identity_property_rejected(self):
        def mutate(data):
            data["tree"]["properties"].append({
                "name": "compatible",
                "type": "string",
                "value": "google,walleye",
                "provenance": "phase2b-platform-identity",
            })
        self.assert_invalid(mutate)

    def test_fixture_byte_bound(self):
        self.assert_invalid(raw_size=4097)

    def test_duplicate_json_object_key_rejected(self):
        with self.assertRaises(MODULE.DuplicateKeyError):
            MODULE.load_json(ROOT / "fixtures" / "adt" / "invalid-duplicate-json-key.json")

    def test_validation_evidence_matches_inputs(self):
        evidence = json.loads((ROOT / "evidence" / "walleye-m3b-validation.json").read_text())
        self.assertEqual(evidence["policy_validation"]["status"], "valid_with_unresolved")
        self.assertEqual(evidence["m2_consistency"]["unresolved_count"], 38)
        self.assertTrue(evidence["m3a_consistency"]["fail_closed"])
        self.assertTrue(evidence["patch_stack"]["patches_0001_0002_present"])
        for relative, expected in evidence["inputs"].items():
            actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, relative)


if __name__ == "__main__":
    unittest.main()
