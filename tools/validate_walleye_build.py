#!/usr/bin/env python3
"""Validate the offline-only WALLEYE M1 build configuration."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

XNU_COMMIT = "1b191cb58250d0705d8a51287127505aa4bc0789"
IOS_SWEET_COMMIT = "45263bee51df4a0f55cdf9c649af886399488ddb"
FEATURE_GATES = {
    "platform_expert",
    "firmware_calls",
    "smp",
    "gic",
    "timer",
    "uart",
    "framebuffer",
    "storage",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping(value: Any, name: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{name}: expected object")
        return {}
    return value


def _new_file_from_patch(patch: str, relative: str) -> str | None:
    marker = f"diff --git a/{relative} b/{relative}\n"
    start = patch.find(marker)
    if start < 0:
        return None
    block = patch[start + len(marker):]
    next_file = block.find("\ndiff --git ")
    if next_file >= 0:
        block = block[:next_file]
    if "new file mode " not in block:
        return None
    lines = block.splitlines()
    try:
        hunk = next(index for index, line in enumerate(lines) if line.startswith("@@ "))
    except StopIteration:
        return None
    return "\n".join(line[1:] for line in lines[hunk + 1:] if line.startswith("+")) + "\n"


def validate(data: dict[str, Any], root: Path) -> list[str]:
    errors: list[str] = []
    if data.get("schema_version") != 1:
        errors.append("/schema_version: expected 1")
    if data.get("milestone") != "M1" or data.get("configuration") != "WALLEYE":
        errors.append("/: expected the M1 WALLEYE configuration")
    if data.get("status") != "compile_only" or data.get("boot_readiness_claimed") is not False:
        errors.append("/: M1 must remain compile-only and make no boot-readiness claim")

    baseline = _mapping(data.get("source_baseline"), "/source_baseline", errors)
    if baseline.get("xnu_commit") != XNU_COMMIT:
        errors.append("/source_baseline/xnu_commit: pinned commit mismatch")
    if baseline.get("ios_sweet_commit") != IOS_SWEET_COMMIT:
        errors.append("/source_baseline/ios_sweet_commit: pinned commit mismatch")
    if baseline.get("sweet_patch_count") != 81:
        errors.append("/source_baseline/sweet_patch_count: expected 81")

    compiler = _mapping(data.get("compiler"), "/compiler", errors)
    if compiler.get("target_triple") != "arm64-apple-darwin22":
        errors.append("/compiler/target_triple: expected arm64-apple-darwin22")
    flags = compiler.get("architecture_flags")
    if flags != ["-march=armv8-a", "-mno-outline-atomics"]:
        errors.append("/compiler/architecture_flags: expected conservative Armv8-A flags")
    if compiler.get("cpu_specific_flags") != []:
        errors.append("/compiler/cpu_specific_flags: M1 must not select a CPU model")
    if compiler.get("machine_definition") != "-DARM64_BOARD_CONFIG_WALLEYE":
        errors.append("/compiler/machine_definition: WALLEYE definition missing")
    if compiler.get("mach_o_architecture") != "arm64":
        errors.append("/compiler/mach_o_architecture: arm64e is not permitted")
    all_flags = " ".join(str(flag).lower() for flag in (flags or []) + (compiler.get("cpu_specific_flags") or []))
    for forbidden in ("armv8.1", "armv8.2", "+crypto", "arm64e", "-mcpu=", "+lse", "+sve"):
        if forbidden in all_flags:
            errors.append(f"/compiler: forbidden unverified feature {forbidden}")

    abi = _mapping(compiler.get("abi_assumptions"), "/compiler/abi_assumptions", errors)
    if abi.get("pointer_authentication") is not False or abi.get("arm64e") is not False:
        errors.append("/compiler/abi_assumptions: PAC/arm64e must be disabled")
    if abi.get("xnu_compile_page_granule_bytes") != 4096:
        errors.append("/compiler/abi_assumptions: expected compile-only 4 KiB default")
    if "unresolved" not in str(abi.get("page_granule_status", "")):
        errors.append("/compiler/abi_assumptions/page_granule_status: runtime state must remain unresolved")

    isa = _mapping(data.get("isa_policy"), "/isa_policy", errors)
    if isa.get("selected_baseline") != "Armv8-A base architecture":
        errors.append("/isa_policy/selected_baseline: expected Armv8-A base")
    if isa.get("unknown_maximal_features") is not True:
        errors.append("/isa_policy/unknown_maximal_features: must remain true")
    disabled = isa.get("not_enabled_without_evidence")
    if not isinstance(disabled, list) or not {"Armv8.2-A", "LSE atomics", "pointer authentication and arm64e"}.issubset(disabled):
        errors.append("/isa_policy/not_enabled_without_evidence: required exclusions missing")

    boundary = _mapping(data.get("machine_boundary"), "/machine_boundary", errors)
    if boundary.get("build_identifier") != "WALLEYE" or boundary.get("board_definition") != "ARM64_BOARD_CONFIG_WALLEYE":
        errors.append("/machine_boundary: distinct WALLEYE identity missing")
    if boundary.get("compile_cpu_limit") != 1:
        errors.append("/machine_boundary/compile_cpu_limit: M1 must remain boot-CPU-only")
    if boundary.get("platform_expert_implemented") is not False:
        errors.append("/machine_boundary/platform_expert_implemented: M3 work is not permitted in M1")
    gates = _mapping(boundary.get("feature_gates"), "/machine_boundary/feature_gates", errors)
    if set(gates) != FEATURE_GATES or any(value is not False for value in gates.values()):
        errors.append("/machine_boundary/feature_gates: every defined hardware gate must be false")

    artifacts = data.get("source_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("/source_artifacts: expected non-empty list")
        artifacts = []
    seen: set[str] = set()
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            errors.append(f"/source_artifacts/{index}: expected object")
            continue
        rel = artifact.get("path")
        expected = artifact.get("sha256")
        if not isinstance(rel, str) or rel.startswith("/") or ".." in Path(rel).parts:
            errors.append(f"/source_artifacts/{index}/path: unsafe path")
            continue
        path = root / rel
        seen.add(rel)
        if not path.is_file():
            errors.append(f"/source_artifacts/{index}/path: missing {rel}")
        elif expected != sha256(path):
            errors.append(f"/source_artifacts/{index}/sha256: mismatch for {rel}")

    required_paths = {
        "patches/xnu/0001-walleye-build-skeleton.patch",
        "overlays/walleye/pexpert/pexpert/arm64/WALLEYE.h",
        "overlays/walleye/config/MASTER.arm64.walleye",
        "overlays/walleye/compile_probe.c",
    }
    if not required_paths.issubset(seen):
        errors.append("/source_artifacts: required patch/overlay paths missing")

    header_path = root / "overlays/walleye/pexpert/pexpert/arm64/WALLEYE.h"
    master_path = root / "overlays/walleye/config/MASTER.arm64.walleye"
    patch_path = root / "patches/xnu/0001-walleye-build-skeleton.patch"
    if header_path.is_file():
        header = header_path.read_text()
        for name in FEATURE_GATES:
            macro = f"WALLEYE_ENABLE_{name.upper()}" if name != "firmware_calls" else "WALLEYE_ENABLE_FIRMWARE_CALLS"
            if f"#define {macro}" not in header or not any(
                line.startswith(f"#define {macro}") and line.split()[-1] == "0" for line in header.splitlines()
            ):
                errors.append(f"WALLEYE.h: {macro} must be defined as 0")
        for forbidden in ("0x9c000000", "xiaomi,sweet", "qcom,kryo470", "SweetCPU", "SweetPlatformExpert", "smc #0"):
            if forbidden.lower() in header.lower():
                errors.append(f"WALLEYE.h: forbidden SWEET dependency {forbidden}")
    if master_path.is_file():
        master = master_path.read_text().lower()
        if "nos_arm_asm nos_arm_pmap" not in master:
            errors.append("MASTER.arm64.walleye: open-source ARM assembly/pmap selection missing")
        for forbidden in ("sweet_hfs", "mockfs", "xiaomi", "0x9c000000"):
            if forbidden in master:
                errors.append(f"MASTER.arm64.walleye: forbidden SWEET dependency {forbidden}")
    if patch_path.is_file():
        patch = patch_path.read_text()
        required_fragments = (
            "MACHINE_FLAGS_ARM64_WALLEYE",
            "-DARM64_BOARD_CONFIG_WALLEYE",
            "-march=armv8-a -mno-outline-atomics",
            "ARM64_BOARD_CONFIG_WALLEYE",
            "config/MASTER.arm64.walleye",
        )
        for fragment in required_fragments:
            if fragment not in patch:
                errors.append(f"patch: missing {fragment}")
        added = "\n".join(line[1:] for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++"))
        for forbidden in ("0x9c000000", "xiaomi,sweet", "qcom,kryo470", "SweetCPU", "SweetPlatformExpert", "smc #0"):
            if forbidden.lower() in added.lower():
                errors.append(f"patch additions: forbidden SWEET dependency {forbidden}")
        for relative, overlay_path in (
            ("pexpert/pexpert/arm64/WALLEYE.h", header_path),
            ("config/MASTER.arm64.walleye", master_path),
        ):
            extracted = _new_file_from_patch(patch, relative)
            if extracted is None or not overlay_path.is_file() or extracted != overlay_path.read_text():
                errors.append(f"patch/overlay mismatch: {relative}")

    unresolved = data.get("unresolved")
    if not isinstance(unresolved, list) or len(unresolved) < 8:
        errors.append("/unresolved: expected explicit firmware/hardware/tooling unknowns")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    config_path = args.config.resolve()
    root = config_path.parent.parent
    data = json.loads(config_path.read_text())
    errors = validate(data, root)
    print(json.dumps({"valid": not errors, "errors": errors}, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
