import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("walleye_validator", ROOT / "tools" / "validate_walleye_build.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)
BASE = json.loads((ROOT / "config" / "walleye-build.json").read_text())


class WalleyeBuildValidatorTests(unittest.TestCase):
    def test_reference_configuration(self):
        self.assertEqual(MODULE.validate(copy.deepcopy(BASE), ROOT), [])

    def test_rejects_armv82(self):
        data = copy.deepcopy(BASE)
        data["compiler"]["architecture_flags"] = ["-march=armv8.2-a+crypto"]
        self.assertTrue(MODULE.validate(data, ROOT))

    def test_rejects_cpu_specific_flag(self):
        data = copy.deepcopy(BASE)
        data["compiler"]["cpu_specific_flags"] = ["-mcpu=cortex-a73"]
        self.assertTrue(MODULE.validate(data, ROOT))

    def test_rejects_enabled_firmware(self):
        data = copy.deepcopy(BASE)
        data["machine_boundary"]["feature_gates"]["firmware_calls"] = True
        self.assertTrue(MODULE.validate(data, ROOT))

    def test_rejects_artifact_hash_mismatch(self):
        data = copy.deepcopy(BASE)
        data["source_artifacts"][0]["sha256"] = "0" * 64
        self.assertTrue(MODULE.validate(data, ROOT))

    def test_patch_is_well_formed(self):
        patch = ROOT / "patches" / "xnu" / "0001-walleye-build-skeleton.patch"
        result = subprocess.run(
            ["git", "apply", "--numstat", str(patch)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pexpert/pexpert/arm64/WALLEYE.h", result.stdout)

    def test_recorded_build_matches_inputs(self):
        result = json.loads((ROOT / "evidence" / "walleye-m1-build.json").read_text())
        self.assertTrue(result["success"])
        self.assertEqual(result["source"]["xnu_commit"], MODULE.XNU_COMMIT)
        self.assertEqual(result["stages"]["patch_application_check"], "passed")
        self.assertEqual(result["stages"]["host_source_compilation"], "passed")
        self.assertEqual(result["stages"]["arm64_macho_source_compilation"], "unavailable")
        self.assertEqual(result["claims"], {"linked": False, "kernel_built": False, "bootable": False})
        for relative, expected in result["inputs"].items():
            actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, relative)


if __name__ == "__main__":
    unittest.main()
