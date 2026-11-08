import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("msm8998_validator", ROOT / "tools" / "validate_msm8998_platform.py")
MOD = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MOD)
BASE = json.loads((ROOT / "config" / "msm8998-platform.json").read_text())


class PlatformValidatorTests(unittest.TestCase):
    def validate(self, mutate=None):
        data = copy.deepcopy(BASE)
        if mutate: mutate(data)
        return MOD.validate(data)

    def test_reference_is_valid_with_explicit_unknowns(self):
        result = self.validate()
        self.assertEqual(result["status"], "valid_with_unresolved")
        self.assertEqual(result["errors"], [])
        self.assertIn("5 dynamic reserved-memory placements", result["unresolved"])

    def test_missing_required_property(self):
        result = self.validate(lambda d: d["timer"].pop("intid"))
        self.assertEqual(result["status"], "invalid")
        self.assertTrue(any("missing required property" in e for e in result["errors"]))

    def test_rejects_uint64_overflow(self):
        result = self.validate(lambda d: d["memory"]["declaration"].__setitem__("end_exclusive", "0x10000000000000000"))
        self.assertTrue(any("unsigned 64-bit" in e for e in result["errors"]))

    def test_rejects_boolean_as_address(self):
        result = self.validate(lambda d: d["storage"]["ufs_controller"].__setitem__("base", True))
        self.assertTrue(any("boolean" in e for e in result["errors"]))

    def test_rejects_unaligned_gic(self):
        result = self.validate(lambda d: d["interrupt_controller"]["distributor"].__setitem__("base", "0x17a00001"))
        self.assertTrue(any("not aligned" in e for e in result["errors"]))

    def test_rejects_unsupported_timer_interrupt(self):
        result = self.validate(lambda d: d["timer"].__setitem__("intid", 40))
        self.assertTrue(any("must use a PPI" in e for e in result["errors"]))

    def test_rejects_overlapping_reservations(self):
        def mutate(d):
            d["reserved_memory"]["inventory_status"] = "complete"
            d["reserved_memory"]["entries"] = [
                {"name":"a","kind":"static","status":"resolved","start":"0x90000000","end_exclusive":"0x90002000"},
                {"name":"b","kind":"static","status":"resolved","start":"0x90001000","end_exclusive":"0x90003000"}]
        result = self.validate(mutate)
        self.assertTrue(any("overlaps" in e for e in result["errors"]))

    def test_rejects_inconsistent_resolved_cpu_topology(self):
        def mutate(d):
            d["cpu"].update({"topology_status":"resolved", "boot_cpu_mpidr":"0x0", "clusters":[],
                             "cpus":[{"logical_id":0,"mpidr":"0x0","cluster_id":0,"boot":True}]})
        result = self.validate(mutate)
        self.assertTrue(any("exactly count entries" in e for e in result["errors"]))

    def test_rejects_guessed_unknown_firmware(self):
        result = self.validate(lambda d: d["firmware"].__setitem__("psci_conduit", "smc"))
        self.assertTrue(any("guessed" in e for e in result["errors"]))

    def test_rejects_missing_provenance(self):
        result = self.validate(lambda d: d["provenance"].pop("/timer/intid"))
        self.assertTrue(any("/timer/intid" in e for e in result["errors"]))

    def test_rejects_mmio_addition_overflow(self):
        def mutate(d):
            d["storage"]["ufs_controller"].update({"base":"0xfffffffffffff000", "size":"0x2000"})
        result = self.validate(mutate)
        self.assertTrue(any("address overflow" in e for e in result["errors"]))
