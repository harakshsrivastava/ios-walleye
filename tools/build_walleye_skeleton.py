#!/usr/bin/env python3
"""Reproducible compile-only validation for the WALLEYE M1 overlay."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "walleye-build.json"
PATCH = ROOT / "patches" / "xnu" / "0001-walleye-build-skeleton.patch"
OVERLAY = ROOT / "overlays" / "walleye"
PROBE = OVERLAY / "compile_probe.c"
XNU_COMMIT = "1b191cb58250d0705d8a51287127505aa4bc0789"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], log: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    log.append("$ " + " ".join(command))
    result = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.stdout:
        log.append(result.stdout.rstrip())
    log.append(f"exit={result.returncode}")
    return result


def tool(names: list[str]) -> str | None:
    for name in names:
        if not name:
            continue
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return None


def artifact(path: Path, out: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(out)),
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True, help="Pinned XNU tree with SWEET patches 0001-0009 applied")
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "walleye-m1")
    args = parser.parse_args()
    source = args.source.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    log: list[str] = []
    failures: list[str] = []

    config = json.loads(CONFIG.read_text())
    validate = run([sys.executable, str(ROOT / "tools" / "validate_walleye_build.py"), str(CONFIG)], log)
    if validate.returncode:
        failures.append("manifest validation failed")

    revision = run(["git", "-C", str(source), "rev-parse", "HEAD"], log)
    source_sha = revision.stdout.strip() if revision.returncode == 0 else None
    if source_sha != XNU_COMMIT:
        failures.append("source is not the pinned XNU commit")

    makeinc = source / "makedefs" / "MakeInc.def"
    board = source / "pexpert" / "pexpert" / "arm64" / "board_config.h"
    source_ready = makeinc.is_file() and board.is_file()
    if source_ready:
        make_text = makeinc.read_text()
        board_text = board.read_text()
        if "MACHINE_FLAGS_ARM64_SWEET" not in make_text or "ARM64_BOARD_CONFIG_SWEET" not in board_text:
            failures.append("required SWEET machine-config prerequisite is absent")
        if "MACHINE_FLAGS_ARM64_WALLEYE" in make_text or "ARM64_BOARD_CONFIG_WALLEYE" in board_text:
            failures.append("source already contains WALLEYE changes; patch check requires the pre-M1 tree")
    else:
        failures.append("source machine-configuration files are missing")

    patch_check = run(["git", "-C", str(source), "apply", "--check", str(PATCH)], log)
    patch_status = "passed" if patch_check.returncode == 0 else "failed"
    if patch_check.returncode:
        failures.append("WALLEYE patch does not apply cleanly")

    cc = tool([os.environ.get("CC", ""), "cc", "gcc"])
    host_object = out / "walleye-config-probe.host.o"
    host_status = "unavailable"
    host_artifact: dict[str, Any] | None = None
    host_version: str | None = None
    if cc:
        version = run([cc, "--version"], log)
        host_version = version.stdout.splitlines()[0] if version.stdout else None
        host_command = [
            cc,
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-ffreestanding",
            "-fno-builtin",
            "-nostdinc",
            "-I",
            str(OVERLAY / "pexpert"),
            "-c",
            str(PROBE),
            "-o",
            str(host_object),
        ]
        host_compile = run(host_command, log)
        host_status = "passed" if host_compile.returncode == 0 else "failed"
        if host_compile.returncode == 0:
            host_artifact = artifact(host_object, out)
        else:
            failures.append("host compile probe failed")

    clang = tool([os.environ.get("WALLEYE_CLANG", ""), "clang-19", "clang-18", "clang"])
    target_object = out / "walleye-config-probe.arm64.o"
    target_status = "unavailable"
    target_artifact: dict[str, Any] | None = None
    target_version: str | None = None
    if clang:
        version = run([clang, "--version"], log)
        target_version = version.stdout.splitlines()[0] if version.stdout else None
        target_command = [
            clang,
            "-target",
            config["compiler"]["target_triple"],
            *config["compiler"]["architecture_flags"],
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-ffreestanding",
            "-fno-builtin",
            "-fno-stack-protector",
            "-nostdinc",
            "-I",
            str(OVERLAY / "pexpert"),
            "-c",
            str(PROBE),
            "-o",
            str(target_object),
        ]
        target_compile = run(target_command, log)
        target_status = "passed" if target_compile.returncode == 0 else "failed"
        if target_compile.returncode == 0:
            raw = target_object.read_bytes()
            if len(raw) < 12 or raw[:4] != b"\xcf\xfa\xed\xfe" or struct.unpack_from("<I", raw, 4)[0] != 0x0100000C:
                target_status = "failed"
                failures.append("target object is not little-endian ARM64 Mach-O")
            else:
                target_artifact = artifact(target_object, out)
        else:
            failures.append("available target compiler rejected the WALLEYE probe")

    inputs = {
        str(path.relative_to(ROOT)): sha256(path)
        for path in (
            CONFIG,
            PATCH,
            OVERLAY / "pexpert" / "pexpert" / "arm64" / "WALLEYE.h",
            OVERLAY / "config" / "MASTER.arm64.walleye",
            PROBE,
        )
    }
    result: dict[str, Any] = {
        "schema_version": 1,
        "milestone": "M1",
        "configuration": "WALLEYE",
        "source": {
            "path": str(source),
            "xnu_commit": source_sha,
            "prerequisite": "SWEET patches 0001-0009",
        },
        "inputs": inputs,
        "stages": {
            "manifest_validation": "passed" if validate.returncode == 0 else "failed",
            "source_provenance": "passed" if source_sha == XNU_COMMIT else "failed",
            "patch_application_check": patch_status,
            "configuration_parsing": {
                "static_manifest": "passed" if validate.returncode == 0 else "failed",
                "xnu_config_tool": "not_attempted: Apple build dependencies unavailable",
            },
            "host_source_compilation": host_status,
            "arm64_macho_source_compilation": target_status,
            "object_generation": {
                "host": host_artifact,
                "arm64_macho": target_artifact,
            },
            "linking": "not_attempted: M1 has no link target",
            "kernel_build": "not_attempted: Apple SDK/KDK build dependencies unavailable",
        },
        "toolchain": {
            "host_compiler": cc,
            "host_compiler_version": host_version,
            "target_compiler": clang,
            "target_compiler_version": target_version,
            "target_triple": config["compiler"]["target_triple"],
            "architecture_flags": config["compiler"]["architecture_flags"],
        },
        "success": not failures,
        "failures": failures,
        "claims": {
            "linked": False,
            "kernel_built": False,
            "bootable": False,
        },
    }
    result_path = out / "build-result.json"
    result_path.write_text(json.dumps(result, indent=2) + "\n")
    (out / "build.log").write_text("\n".join(log) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
