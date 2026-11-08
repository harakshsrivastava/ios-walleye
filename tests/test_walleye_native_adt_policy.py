import copy
import ctypes
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


PYTHON_POLICY = load_module(
    "m3c_python_policy", ROOT / "tools" / "validate_walleye_adt.py"
)
POLICY = json.loads((ROOT / "config" / "walleye-adt-policy.json").read_text())
BASE = json.loads((ROOT / "fixtures" / "adt" / "minimal-structural.json").read_text())
CONFIG = json.loads((ROOT / "config" / "walleye-native-adt-policy.json").read_text())


class Span(ctypes.Structure):
    _fields_ = [
        ("data", ctypes.POINTER(ctypes.c_uint8)),
        ("length", ctypes.c_uint32),
        ("capacity", ctypes.c_uint32),
    ]


class Node(ctypes.Structure):
    _fields_ = [
        ("path", Span),
        ("parent_index", ctypes.c_uint16),
        ("depth", ctypes.c_uint8),
        ("node_type", ctypes.c_uint8),
    ]


class Property(ctypes.Structure):
    _fields_ = [
        ("name", Span),
        ("value", Span),
        ("node_index", ctypes.c_uint16),
        ("property_type", ctypes.c_uint8),
        ("reserved", ctypes.c_uint8),
    ]


class UnsupportedMapping(ValueError):
    pass


class NormalizedFixture:
    def __init__(self, fixture):
        self.buffers = []
        self.nodes = []
        self.properties = []
        self._check_metadata(fixture)
        self._flatten(fixture["tree"], 0xffff, 0)
        self.node_array = (Node * len(self.nodes))(*self.nodes)
        self.property_array = (Property * len(self.properties))(*self.properties)
        self.logical_size = (
            len(self.nodes) * 16
            + len(self.properties) * 24
            + sum(node.path.length for node in self.nodes)
            + sum(prop.name.length + prop.value.length for prop in self.properties)
        )

    def _check_metadata(self, fixture):
        for key in ("fixture_format", "policy_version", "producer", "identity", "runtime"):
            if fixture.get(key) != BASE.get(key):
                raise UnsupportedMapping(f"metadata outside native normalized representation: {key}")
        if not isinstance(fixture.get("tree"), dict):
            raise UnsupportedMapping("tree is not a normalized node object")

    def _span(self, value):
        data = value if isinstance(value, bytes) else value.encode("utf-8")
        array = (ctypes.c_uint8 * max(1, len(data)))()
        if data:
            ctypes.memmove(array, data, len(data))
        self.buffers.append(array)
        return Span(ctypes.cast(array, ctypes.POINTER(ctypes.c_uint8)), len(data), len(data))

    def _flatten(self, node, parent, depth):
        if not isinstance(node, dict):
            raise UnsupportedMapping("tree member is not a node object")
        index = len(self.nodes)
        type_map = {"root": 1, "structural": 2, "hardware": 3}
        self.nodes.append(Node(
            self._span(node.get("path", "")),
            parent,
            depth,
            type_map.get(node.get("node_type"), 0xff),
        ))
        type_values = {"string": 1, "string-list": 2, "uint32": 3,
                       "uint64": 4, "boolean": 5, "data": 6}
        properties = node.get("properties")
        children = node.get("children")
        if not isinstance(properties, list) or not isinstance(children, list):
            raise UnsupportedMapping("properties and children must be arrays")
        for prop in properties:
            value = prop.get("value")
            if isinstance(value, str):
                encoded = value.encode("utf-8")
            elif isinstance(value, bool):
                encoded = bytes([1 if value else 0])
            elif isinstance(value, int):
                encoded = value.to_bytes(8, "little", signed=False)
            elif isinstance(value, list) and all(isinstance(item, str) for item in value):
                encoded = b"\0".join(item.encode("utf-8") for item in value) + b"\0"
            else:
                encoded = b""
            self.properties.append(Property(
                self._span(prop.get("name", "")),
                self._span(encoded),
                index,
                type_values.get(prop.get("type"), 0xff),
                0,
            ))
        for child in children:
            self._flatten(child, index, depth + 1)


class WalleyeNativeAdtPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.temp.name) / "build"
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "build_walleye_adt_policy.py"),
             "--out", str(cls.out)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stdout)
        cls.build = json.loads(result.stdout)
        cls.library = ctypes.CDLL(str(cls.out / "host" / "libwalleye_adt_policy.so"))
        cls.validate = cls.library.walleye_validate_normalized_adt
        cls.validate.argtypes = [
            ctypes.c_uint32,
            ctypes.POINTER(Node), ctypes.c_uint32,
            ctypes.POINTER(Property), ctypes.c_uint32,
            ctypes.c_uint32,
        ]
        cls.validate.restype = ctypes.c_int

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def native(self, fixture):
        normalized = NormalizedFixture(fixture)
        result = self.validate(
            1,
            normalized.node_array, len(normalized.nodes),
            normalized.property_array, len(normalized.properties),
            normalized.logical_size,
        )
        return result

    def python_valid(self, fixture):
        status, _, _ = PYTHON_POLICY.validate_fixture(fixture, POLICY, ROOT)
        return status != "invalid"

    def test_arm64_macho_is_reproducible(self):
        arm = self.build["arm64_macho"]
        self.assertTrue(self.build["success"])
        self.assertEqual(arm["runs"], 2)
        self.assertTrue(arm["byte_identical"])
        self.assertEqual(arm["object"]["format"], "Mach-O 64-bit arm64 MH_OBJECT")
        self.assertEqual(arm["object"]["size_bytes"], 4128)
        self.assertEqual(
            arm["object"]["sha256"],
            "3a4c5eabcf96aaa53a234bc44e1a41c4b132e61e2e9c1e02810d83652917a3cb",
        )

    def test_host_and_sanitizer_runs_pass(self):
        host = self.build["host_validation"]
        self.assertEqual(host["test_status"], "passed")
        self.assertEqual(host["asan_ubsan_status"], "passed")
        self.assertEqual(host["differential_library_status"], "passed")

    def test_supported_differential_cases_agree(self):
        cases = []
        cases.append(("minimal", copy.deepcopy(BASE)))
        root_only = copy.deepcopy(BASE)
        root_only["tree"]["children"] = []
        cases.append(("root-only", root_only))
        duplicate_property = copy.deepcopy(BASE)
        duplicate_property["tree"]["properties"].append(
            copy.deepcopy(duplicate_property["tree"]["properties"][0])
        )
        cases.append(("duplicate-property", duplicate_property))
        unknown_node = copy.deepcopy(BASE)
        unknown_node["tree"]["children"][0]["path"] = "/mystery"
        cases.append(("unknown-node", unknown_node))
        hardware = copy.deepcopy(BASE)
        hardware["tree"]["children"][0].update({"path": "/gpu", "node_type": "hardware"})
        cases.append(("hardware-node", hardware))
        oversized = copy.deepcopy(BASE)
        oversized["tree"]["properties"][0]["value"] = "x" * 65
        cases.append(("oversized-property", oversized))
        bad_root = copy.deepcopy(BASE)
        bad_root["tree"]["properties"][0]["value"] = "sweet"
        cases.append(("bad-root", bad_root))
        bad_chosen = copy.deepcopy(BASE)
        bad_chosen["tree"]["children"][0]["properties"][0]["value"] = "wrong"
        cases.append(("bad-chosen", bad_chosen))
        bad_type = copy.deepcopy(BASE)
        bad_type["tree"]["properties"][0]["type"] = "uint32"
        cases.append(("bad-type", bad_type))
        identity_property = copy.deepcopy(BASE)
        identity_property["tree"]["properties"].append({
            "name": "compatible", "type": "string", "value": "xiaomi,sweet",
            "provenance": "phase2b-platform-identity",
        })
        cases.append(("sweet-identity-property", identity_property))
        deep = copy.deepcopy(BASE)
        deep["tree"]["children"][0]["children"].append({
            "path": "/chosen/extra", "node_type": "structural",
            "properties": [], "children": [],
        })
        cases.append(("excessive-depth", deep))
        duplicate_chosen = copy.deepcopy(BASE)
        duplicate_chosen["tree"]["children"].append(
            copy.deepcopy(duplicate_chosen["tree"]["children"][0])
        )
        cases.append(("duplicate-chosen", duplicate_chosen))
        bad_path = copy.deepcopy(BASE)
        bad_path["tree"]["path"] = "root"
        cases.append(("invalid-path", bad_path))
        for name, fixture in cases:
            with self.subTest(name=name):
                python_decision = self.python_valid(fixture)
                native_decision = self.native(fixture) == 0
                self.assertEqual(native_decision, python_decision)

    def test_unrepresentable_metadata_is_not_silently_equated(self):
        runtime = copy.deepcopy(BASE)
        runtime["runtime"]["platform_expert_start_enabled"] = True
        self.assertFalse(self.python_valid(runtime))
        with self.assertRaises(UnsupportedMapping):
            NormalizedFixture(runtime)
        identity = copy.deepcopy(BASE)
        identity["identity"]["physical_board"]["product"] = "Xiaomi SWEET"
        self.assertFalse(self.python_valid(identity))
        with self.assertRaises(UnsupportedMapping):
            NormalizedFixture(identity)

    def test_null_pointer_nonzero_length(self):
        normalized = NormalizedFixture(BASE)
        normalized.property_array[0].value.data = ctypes.POINTER(ctypes.c_uint8)()
        result = self.validate(
            1, normalized.node_array, len(normalized.nodes),
            normalized.property_array, len(normalized.properties), normalized.logical_size,
        )
        self.assertEqual(result, CONFIG["stable_results"]["WALLEYE_ADT_INVALID_ARGUMENT"])

    def test_truncated_value_buffer(self):
        normalized = NormalizedFixture(BASE)
        normalized.property_array[0].value.capacity = 1
        result = self.validate(
            1, normalized.node_array, len(normalized.nodes),
            normalized.property_array, len(normalized.properties), normalized.logical_size,
        )
        self.assertEqual(result, CONFIG["stable_results"]["WALLEYE_ADT_BOUNDS_VIOLATION"])

    def test_integer_count_overflow(self):
        normalized = NormalizedFixture(BASE)
        result = self.validate(
            1, normalized.node_array, 0xffffffff,
            normalized.property_array, len(normalized.properties), normalized.logical_size,
        )
        self.assertEqual(result, CONFIG["stable_results"]["WALLEYE_ADT_BOUNDS_VIOLATION"])

    def test_stable_results_and_policy_limits(self):
        self.assertEqual(list(CONFIG["stable_results"].values()), list(range(9)))
        self.assertEqual(CONFIG["policy_limits"]["maximum_nodes"], 2)
        self.assertEqual(CONFIG["policy_limits"]["maximum_depth"], 1)
        self.assertEqual(CONFIG["policy_limits"]["maximum_property_size_bytes"], 64)
        self.assertEqual(CONFIG["policy_limits"]["maximum_normalized_size_bytes"], 4096)

    def test_helper_has_no_runtime_or_hardware_dependencies(self):
        source = (ROOT / "src" / "walleye_adt_policy.c").read_text()
        for forbidden in (
            "malloc", "calloc", "realloc", "free(", "IOKit", "SecureDT",
            "IODT", "smc", "asm(", "0x17a00000", "0x17b00000", "xiaomi",
        ):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("walleye_validate_normalized_adt(", source.split(
            "walleye_validate_normalized_adt(", 1)[1])

    def test_host_harness_covers_required_adversarial_cases(self):
        source = (ROOT / "tests" / "native" / "walleye_adt_policy_test.c").read_text()
        for label in (
            "missing root", "duplicate root", "duplicate chosen", "unknown node",
            "unknown property", "sweet identity", "invalid root name",
            "invalid chosen name", "oversized property", "oversized fixture",
            "excessive depth", "invalid path", "invalid property type",
            "null pointer nonzero length", "truncated value", "integer/count overflow",
            "invalid parent", "unsupported version",
        ):
            self.assertIn(label, source)

    def test_previous_guarantees_remain_fail_closed(self):
        preserved = CONFIG["preserved_guarantees"]
        self.assertEqual(preserved["m2_status"], "valid_with_unresolved")
        self.assertEqual(preserved["m2_unresolved_count"], 38)
        self.assertEqual(preserved["m3b_policy_unresolved_count"], 4)
        self.assertFalse(preserved["platform_expert_match_enabled"])
        self.assertFalse(preserved["platform_expert_start_supported"])
        self.assertEqual(preserved["iokit_node_publication"], "none")
        self.assertFalse(preserved["native_adt_parser"])
        self.assertFalse(preserved["hardware_initialization"])
        self.assertFalse(preserved["boot_ready"])

    def test_manifest_hashes_match_sources(self):
        for item in CONFIG["sources"]:
            actual = hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest()
            self.assertEqual(actual, item["sha256"], item["path"])

    def test_validation_evidence_matches_inputs(self):
        evidence = json.loads((ROOT / "evidence" / "walleye-m3c-validation.json").read_text())
        self.assertTrue(evidence["compile_validation"]["byte_identical"])
        self.assertEqual(
            evidence["compile_validation"]["object_sha256"],
            "3a4c5eabcf96aaa53a234bc44e1a41c4b132e61e2e9c1e02810d83652917a3cb",
        )
        self.assertEqual(evidence["differential_validation"]["mismatches"], 0)
        for relative, expected in evidence["inputs"].items():
            actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, relative)


if __name__ == "__main__":
    unittest.main()
