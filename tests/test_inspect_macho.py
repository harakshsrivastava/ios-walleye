import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("inspect_macho", Path(__file__).parents[1] / "tools" / "inspect_macho.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def fixture(command=b""):
    return struct.pack("<IiiIIIII", MOD.MH_MAGIC_64, MOD.CPU_TYPE_ARM64, 0, 2,
                       1 if command else 0, len(command), 0x200001, 0) + command


class MachOTests(unittest.TestCase):
    def parse(self, blob):
        with tempfile.NamedTemporaryFile() as f:
            f.write(blob); f.flush()
            return MOD.inspect(f.name)

    def test_minimal_arm64_execute(self):
        result = self.parse(fixture())
        self.assertEqual(result["header"]["architecture"], "arm64")
        self.assertEqual(result["header"]["filetype_name"], "MH_EXECUTE")

    def test_main_entry(self):
        command = struct.pack("<IIQQ", MOD.LC_MAIN, 24, 0x1234, 0)
        self.assertEqual(self.parse(fixture(command))["entry"]["file_offset"], 0x1234)

    def test_rejects_truncated_commands(self):
        blob = struct.pack("<IiiIIIII", MOD.MH_MAGIC_64, MOD.CPU_TYPE_ARM64, 0, 2, 1, 8, 0, 0)
        with self.assertRaises(MOD.MachOError): self.parse(blob)

    def test_rejects_out_of_bounds_segment(self):
        command = struct.pack("<II16sQQQQiiII", MOD.LC_SEGMENT_64, 72, b"__TEXT", 0, 1, 999, 1, 7, 5, 0, 0)
        with self.assertRaises(MOD.MachOError): self.parse(fixture(command))
