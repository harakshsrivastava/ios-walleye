import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "walleye_platform_expert_validator",
    ROOT / "tools" / "validate_walleye_platform_expert.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)
BASE = json.loads((ROOT / "config" / "walleye-platform-expert.json").read_text())
PATCH = ROOT / "patches" / "xnu" / "0002-walleye-platform-expert.patch"


class WalleyePlatformExpertTests(unittest.TestCase):
    def test_reference_manifest(self):
        self.assertEqual(MODULE.validate(copy.deepcopy(BASE), ROOT), [])

    def test_patch_is_well_formed(self):
        result = subprocess.run(
            ["git", "apply", "--numstat", str(PATCH)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("iokit/Kernel/arm/WalleyePlatformExpert.cpp", result.stdout)

    def test_walleye_and_sweet_classes_are_separate(self):
        patch = PATCH.read_text()
        source = MODULE.added_file_from_patch(
            patch, "iokit/Kernel/arm/WalleyePlatformExpert.cpp"
        )
        self.assertIn("class WalleyePlatformExpert : public IODTPlatformExpert", source)
        self.assertNotIn("SweetPlatformExpert", source)
        self.assertIn("+#endif\n+#if defined(ARM64_BOARD_CONFIG_WALLEYE)", patch)

    def test_identity_match_is_disabled_sentinel(self):
        integration = BASE["source_integration"]
        self.assertEqual(integration["io_name_match"], "__walleye_m3a_disabled__")
        self.assertEqual(integration["match_token_status"], "compile-only-sentinel")
        self.assertFalse(integration["runtime_match_enabled"])
        self.assertEqual(integration["final_adt_identity"], {"value": None, "status": "unresolved"})

    def test_unsupported_operations_fail_explicitly(self):
        source = MODULE.added_file_from_patch(
            PATCH.read_text(), "iokit/Kernel/arm/WalleyePlatformExpert.cpp"
        )
        self.assertIn("WalleyePlatformExpert::start", source)
        self.assertIn("return false;", source)
        self.assertIn("return kIOReturnUnsupported;", source)
        self.assertIn("sleep firmware contract is unresolved", source)
        self.assertNotIn("IODTPlatformExpert::start", source)

    def test_no_sweet_or_peripheral_assumptions(self):
        source = MODULE.added_file_from_patch(
            PATCH.read_text(), "iokit/Kernel/arm/WalleyePlatformExpert.cpp"
        ).lower()
        for fragment in BASE["forbidden_source_fragments"]:
            self.assertNotIn(fragment.lower(), source)
        for fragment in ("createnubs", "childfrompath", "framebuffer", "uart", "psci"):
            self.assertNotIn(fragment, source)

    def test_m2_contract_remains_enforced(self):
        status, errors, unresolved = MODULE._m2_result(ROOT)
        self.assertEqual(status, "valid_with_unresolved")
        self.assertEqual(errors, [])
        self.assertEqual(len(unresolved), 38)
        self.assertEqual(BASE["m2_boundary"]["requirements_resolved_by_m3a"], 0)

    def test_rejects_runtime_start_enablement(self):
        data = copy.deepcopy(BASE)
        data["behavior"]["start_supported"] = True
        self.assertTrue(MODULE.validate(data, ROOT))

    def test_rejects_invented_adt_identity(self):
        data = copy.deepcopy(BASE)
        data["source_integration"]["final_adt_identity"] = {
            "value": "google,walleye",
            "status": "verified",
        }
        self.assertTrue(MODULE.validate(data, ROOT))

    def test_rejects_sweet_isa_flags(self):
        data = copy.deepcopy(BASE)
        data["compiler"]["architecture_flags"] = ["-march=armv8.2-a+crypto"]
        self.assertTrue(MODULE.validate(data, ROOT))

    def test_validation_evidence_matches_inputs(self):
        evidence = json.loads((ROOT / "evidence" / "walleye-m3a-validation.json").read_text())
        self.assertEqual(evidence["full_patch_stack"]["sweet_patches_applied"], 81)
        self.assertTrue(evidence["full_patch_stack"]["m1_applied"])
        self.assertTrue(evidence["full_patch_stack"]["m3a_applied"])
        self.assertEqual(
            evidence["compile_validation"]["policy_probe"]["object_sha256"],
            "67a7cce9bcaf9c4c7f9d7ebd2fbd931464f4cfbe7478cf4bdcfe3910c2d7a69a",
        )
        for relative, expected in evidence["inputs"].items():
            actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, relative)


if __name__ == "__main__":
    unittest.main()
