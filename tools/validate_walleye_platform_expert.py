#!/usr/bin/env python3
"""Validate the compile-only WALLEYE M3A Platform Expert boundary."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_XNU = "1b191cb58250d0705d8a51287127505aa4bc0789"
EXPECTED_SWEET = "45263bee51df4a0f55cdf9c649af886399488ddb"
EXPECTED_FLAGS = ["-march=armv8-a", "-mno-outline-atomics"]
PATCHES = [
    "patches/xnu/0001-walleye-build-skeleton.patch",
    "patches/xnu/0002-walleye-platform-expert.patch",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def added_file_from_patch(patch: str, path: str) -> str:
    marker = f"diff --git a/{path} b/{path}"
    if marker not in patch:
        return ""
    block = patch.split(marker, 1)[1]
    block = block.split("\ndiff --git ", 1)[0]
    if "--- /dev/null" not in block:
        return ""
    lines = block.splitlines()
    output: list[str] = []
    in_hunk = False
    for line in lines:
        if line.startswith("@@"):
            in_hunk = True
        elif in_hunk and line.startswith("+") and not line.startswith("+++"):
            output.append(line[1:])
    return "\n".join(output) + ("\n" if output else "")


def _m2_result(root: Path) -> tuple[str, list[str], list[str]]:
    spec = importlib.util.spec_from_file_location(
        "walleye_boot_contract_validator",
        root / "tools" / "validate_walleye_boot_contract.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    contract = json.loads((root / "config" / "walleye-boot-contract.json").read_text())
    platform = json.loads((root / "config" / "msm8998-platform.json").read_text())
    return module.validate(contract, platform)


def validate(data: dict[str, Any], root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version", "milestone", "configuration", "source_baseline",
        "patch_sequence", "source_integration", "verified_identity", "behavior",
        "compiler", "m2_boundary", "forbidden_source_fragments", "claims",
    }
    missing = sorted(required - data.keys())
    if missing:
        return [f"missing required fields: {', '.join(missing)}"]

    if data["schema_version"] != 1 or data["milestone"] != "M3A":
        errors.append("unsupported schema or milestone")
    if data["configuration"] != "WALLEYE":
        errors.append("configuration must be WALLEYE")

    baseline = data["source_baseline"]
    if baseline.get("xnu_commit") != EXPECTED_XNU:
        errors.append("XNU commit drift")
    if baseline.get("ios_sweet_commit") != EXPECTED_SWEET:
        errors.append("ios-sweet commit drift")
    if baseline.get("sweet_patch_count") != 81:
        errors.append("complete SWEET patch count must remain 81")

    sequence = data["patch_sequence"]
    if not isinstance(sequence, list) or [item.get("path") for item in sequence] != PATCHES:
        errors.append("patch sequence must be M1 followed by M3A")
    else:
        for item in sequence:
            path = root / item["path"]
            if not path.is_file() or item.get("sha256") != sha256(path):
                errors.append(f"patch hash mismatch: {item['path']}")

    integration = data["source_integration"]
    expected_integration = {
        "class": "WalleyePlatformExpert",
        "base_class": "IODTPlatformExpert",
        "build_guard": "ARM64_BOARD_CONFIG_WALLEYE",
        "board_guard": "WALLEYE",
        "provider_class": "IOPlatformExpertDevice",
        "io_name_match": "__walleye_m3a_disabled__",
        "match_token_status": "compile-only-sentinel",
        "runtime_match_enabled": False,
    }
    for key, expected in expected_integration.items():
        if integration.get(key) != expected:
            errors.append(f"source_integration.{key} must be {expected!r}")
    adt = integration.get("final_adt_identity", {})
    if adt.get("value") is not None or adt.get("status") != "unresolved":
        errors.append("final ADT identity must remain unresolved")

    identity = data["verified_identity"]
    if identity.get("target_name") != "walleye" or identity.get("product_name") != "Google Pixel 2":
        errors.append("verified board identity drift")
    if identity.get("does_not_define_adt_compatible") is not True:
        errors.append("board identity must not claim an ADT compatible value")

    behavior = data["behavior"]
    disabled = (
        "start_supported", "firmware_calls", "smp", "gic_initialization",
        "timer_initialization", "uart", "framebuffer", "storage",
    )
    for key in disabled:
        if behavior.get(key) is not False:
            errors.append(f"behavior.{key} must remain false")
    if behavior.get("adt_node_publication") != "none":
        errors.append("ADT node publication must remain disabled")
    if behavior.get("platform_functions") != "unsupported:kIOReturnUnsupported":
        errors.append("platform functions must fail explicitly")

    compiler = data["compiler"]
    if compiler.get("target_triple") != "arm64-apple-darwin22":
        errors.append("compiler target drift")
    if compiler.get("architecture_flags") != EXPECTED_FLAGS:
        errors.append("architecture flags drift")
    actual = compiler.get("actual_translation_unit", {})
    if actual.get("status") != "blocked_by_generated_xnu_headers" or actual.get("object_generated") is not False:
        errors.append("actual source compile boundary is misreported")
    probe = compiler.get("policy_probe", {})
    probe_path = root / str(probe.get("source", ""))
    if not probe_path.is_file() or probe.get("source_sha256") != sha256(probe_path):
        errors.append("policy probe source hash mismatch")
    if probe.get("status") != "passed" or probe.get("byte_identical") is not True:
        errors.append("policy probe result must record reproducible success")
    if probe.get("linked") is not False:
        errors.append("policy probe must not claim linking")

    status, m2_errors, unresolved = _m2_result(root)
    boundary = data["m2_boundary"]
    if status != "valid_with_unresolved" or m2_errors or len(unresolved) != 38:
        errors.append("M2 reference contract no longer has the recorded status")
    if boundary.get("status") != status or boundary.get("unresolved_count") != len(unresolved):
        errors.append("M2 boundary metadata drift")
    if boundary.get("boot_ready") is not False or boundary.get("requirements_resolved_by_m3a") != 0:
        errors.append("M3A must not resolve or bypass boot-critical M2 requirements")

    patch_path = root / PATCHES[1]
    patch_text = patch_path.read_text() if patch_path.is_file() else ""
    source = added_file_from_patch(patch_text, integration.get("translation_unit", ""))
    if "class WalleyePlatformExpert : public IODTPlatformExpert" not in source:
        errors.append("WalleyePlatformExpert source is missing from M3A patch")
    if "WalleyePlatformExpert::start" not in source or "return false;" not in source:
        errors.append("Platform Expert startup must fail closed")
    if "createNubs" in source or "childFromPath" in source or "IODTPlatformExpert::start" in source:
        errors.append("M3A source must not publish or consume unvalidated ADT nodes")
    if "return kIOReturnUnsupported;" not in source or "sleep firmware contract is unresolved" not in source:
        errors.append("unsupported firmware behavior is not explicit")
    for fragment in data["forbidden_source_fragments"]:
        if fragment.lower() in source.lower():
            errors.append(f"SWEET or unverified fragment leaked into WALLEYE source: {fragment}")

    for key, value in data["claims"].items():
        if value is not False:
            errors.append(f"claims.{key} must remain false")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", nargs="?", type=Path,
                        default=ROOT / "config" / "walleye-platform-expert.json")
    args = parser.parse_args()
    try:
        data = json.loads(args.manifest.read_text())
        errors = validate(data, ROOT)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        errors = [str(exc)]
    print(json.dumps({"valid": not errors, "errors": errors}, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
