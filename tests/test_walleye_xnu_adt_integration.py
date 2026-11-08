#!/usr/bin/env python3
"""Static boundary checks for the isolated M3D XNU staging patch."""

from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/xnu/0003-walleye-native-adt-policy.patch"
HEADER = ROOT / "include/walleye_adt_policy.h"
SOURCE = ROOT / "src/walleye_adt_policy.c"
M3A_PATCH = ROOT / "patches/xnu/0002-walleye-platform-expert.patch"


def added_file(patch: str, path: str) -> str:
    marker = f"diff --git a/{path} b/{path}"
    block = patch.split(marker, 1)[1].split("\ndiff --git ", 1)[0]
    lines: list[str] = []
    hunk = False
    for line in block.splitlines():
        if line.startswith("@@"):
            hunk = True
        elif hunk and line.startswith("+") and not line.startswith("+++"):
            lines.append(line[1:])
    return "\n".join(lines) + "\n"


def normalized_xnu_source(text: str) -> str:
    text = text.replace('#include "WalleyeADTPolicy.h"', '#include "walleye_adt_policy.h"', 1)
    text = text.replace("\n#if defined(ARM64_BOARD_CONFIG_WALLEYE)\n", "", 1)
    return text.replace("\n#endif /* ARM64_BOARD_CONFIG_WALLEYE */\n", "\n", 1)


class WalleyeXnuAdtIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.patch = PATCH.read_text()
        cls.header = added_file(cls.patch, "iokit/Kernel/arm/WalleyeADTPolicy.h")
        cls.source = added_file(cls.patch, "iokit/Kernel/arm/WalleyeADTPolicy.c")

    def test_patch_has_expected_three_file_scope(self) -> None:
        paths = [line.split(" b/", 1)[1] for line in self.patch.splitlines() if line.startswith("diff --git ")]
        self.assertEqual(paths, [
            "iokit/conf/files.arm64",
            "iokit/Kernel/arm/WalleyeADTPolicy.h",
            "iokit/Kernel/arm/WalleyeADTPolicy.c",
        ])

    def test_header_is_byte_identical_to_m3c_public_interface(self) -> None:
        self.assertEqual(self.header.encode(), HEADER.read_bytes())

    def test_implementation_is_m3c_equivalent_under_build_guard(self) -> None:
        self.assertIn("#if defined(ARM64_BOARD_CONFIG_WALLEYE)", self.source)
        self.assertIn("#endif /* ARM64_BOARD_CONFIG_WALLEYE */", self.source)
        self.assertEqual(hashlib.sha256(normalized_xnu_source(self.source).encode()).hexdigest(),
                         hashlib.sha256(SOURCE.read_bytes()).hexdigest())

    def test_verified_arm64_source_list_registration_exists(self) -> None:
        self.assertIn("iokit/Kernel/arm/WalleyeADTPolicy.c                              optional iokitcpp", self.patch)

    def test_helper_has_no_runtime_call_site_or_hardware_dependency(self) -> None:
        self.assertEqual(self.source.count("walleye_validate_normalized_adt("), 1)
        for forbidden in ("IOKit", "IODT", "PE_init_platform", "createNubs", "processTopLevel", "SMC", "PSCI", "ICC_", "GICD", "UART", "framebuffer"):
            self.assertNotIn(forbidden.lower(), self.source.lower())

    def test_m3a_fail_closed_source_is_unchanged(self) -> None:
        m3a = M3A_PATCH.read_text()
        self.assertIn("WalleyePlatformExpert::start", m3a)
        self.assertIn("return false;", m3a)
        self.assertNotIn("walleye_validate_normalized_adt", m3a)


if __name__ == "__main__":
    unittest.main()
