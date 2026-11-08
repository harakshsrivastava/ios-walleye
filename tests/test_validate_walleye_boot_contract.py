import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "boot_contract_validator", ROOT / "tools" / "validate_walleye_boot_contract.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)
BASE = json.loads((ROOT / "config" / "walleye-boot-contract.json").read_text())
PLATFORM = json.loads((ROOT / "config" / "msm8998-platform.json").read_text())


class WalleyeBootContractTests(unittest.TestCase):
    def check(self, mutate):
        data = copy.deepcopy(BASE)
        mutate(data)
        return MODULE.validate(data, PLATFORM)

    def assert_invalid(self, mutate):
        status, errors, _ = self.check(mutate)
        self.assertEqual(status, "invalid")
        self.assertTrue(errors)

    def test_reference_is_valid_with_unresolved(self):
        status, errors, unresolved = MODULE.validate(copy.deepcopy(BASE), PLATFORM)
        self.assertEqual(status, "valid_with_unresolved")
        self.assertEqual(errors, [])
        self.assertTrue(unresolved)

    def test_missing_required_field(self):
        self.assert_invalid(lambda data: data.pop("boot_args"))

    def test_invalid_board_identity(self):
        self.assert_invalid(lambda data: data["board"].__setitem__("codename", "sweet"))

    def test_wrong_device_tree_format(self):
        self.assert_invalid(
            lambda data: data["device_tree"]["handoff"].__setitem__("format", "linux-fdt-v17")
        )

    def test_overlapping_memory_ranges(self):
        def mutate(data):
            duplicate = copy.deepcopy(data["physical_memory"]["regions"][0])
            duplicate["id"] = "overlap"
            duplicate["start"] = "0x80001000"
            data["physical_memory"]["regions"].append(duplicate)
        self.assert_invalid(mutate)

    def test_overflowing_memory_range(self):
        def mutate(data):
            region = data["physical_memory"]["regions"][0]
            region["start"] = "0xfffffffffffff000"
            region["size"] = "0x2000"
        self.assert_invalid(mutate)

    def test_reservation_outside_declared_ram(self):
        def mutate(data):
            data["reserved_memory"]["entries"].append({
                "id": "outside",
                "start": "0x1000",
                "size": "0x1000",
                "alignment": "0x1000",
                "status": "historical-report",
                "provenance": "runtime-fdt-reserved-summary",
            })
        self.assert_invalid(mutate)

    def test_unsupported_schema_version(self):
        self.assert_invalid(lambda data: data.__setitem__("schema_version", 2))

    def test_unsupported_contract_version(self):
        self.assert_invalid(lambda data: data["contract"].__setitem__("version", 2))

    def test_unverified_firmware_assumption(self):
        def mutate(data):
            data["firmware_services"]["psci"] = {
                "version": "1.1", "conduit": "smc", "cpu_on": True, "status": "assumed"
            }
        self.assert_invalid(mutate)

    def test_incorrect_initialization_dependency(self):
        self.assert_invalid(
            lambda data: data["initialization_dependencies"][3].__setitem__("depends_on", ["entry-state"])
        )

    def test_invalid_provenance(self):
        self.assert_invalid(lambda data: data["provenance"].pop("runtime-fdt-gicd"))

    def test_guessed_loader_address(self):
        def mutate(data):
            data["kernel_image"]["physical_load_address"] = {
                "value": "0x80080000", "status": "guessed"
            }
        self.assert_invalid(mutate)

    def test_sweet_only_value_leak(self):
        def mutate(data):
            data["board"]["adt_identity"]["status"] = "historical-report"
            data["board"]["adt_identity"]["model"] = "xiaomi,sweet"
        self.assert_invalid(mutate)

    def test_boot_ready_claim_rejected(self):
        self.assert_invalid(lambda data: data["contract"].__setitem__("boot_ready", True))

    def test_validation_evidence_matches_sources(self):
        evidence = json.loads((ROOT / "evidence" / "walleye-m2-validation.json").read_text())
        self.assertEqual(evidence["full_sweet_patch_stack"]["patches_applied"], 81)
        self.assertTrue(evidence["full_sweet_patch_stack"]["m1_patch"]["applies_after_81"])
        self.assertTrue(evidence["arm64_macho_compile"]["byte_identical"])
        self.assertEqual(
            evidence["arm64_macho_compile"]["object"]["sha256"],
            "c9e26b60b2a8e31582de3243cd3c4194998d1cd9066e9329494aa266569fbb21",
        )
        for relative, expected in evidence["contract_validation"]["inputs"].items():
            actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, relative)


if __name__ == "__main__":
    unittest.main()
