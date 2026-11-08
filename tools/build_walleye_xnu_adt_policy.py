#!/usr/bin/env python3
"""Compile-only validation for the M3D XNU-staged WALLEYE ADT helper.

This does not invoke the XNU build system.  It checks the isolated patch against
an existing M1/M3A XNU worktree, stages only the affected XNU paths in a
temporary repository, applies the patch, and compiles its C translation unit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/xnu/0003-walleye-native-adt-policy.patch"
M3C_HEADER = ROOT / "include/walleye_adt_policy.h"
M3C_SOURCE = ROOT / "src/walleye_adt_policy.c"
XNU_COMMIT = "1b191cb58250d0705d8a51287127505aa4bc0789"
TARGET = "arm64-apple-darwin22"
ARCH_FLAGS = ["-march=armv8-a", "-mno-outline-atomics"]
SOURCE_LIST = "iokit/conf/files.arm64"
XNU_HEADER = "iokit/Kernel/arm/WalleyeADTPolicy.h"
XNU_SOURCE = "iokit/Kernel/arm/WalleyeADTPolicy.c"


def run(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compiler_path() -> str | None:
    candidate = Path("/workspace/toolchains/llvm19/usr/lib/llvm-19/bin/clang")
    if candidate.is_file():
        return str(candidate)
    return shutil.which("clang")


def macho_info(path: Path) -> dict[str, Any] | None:
    data = path.read_bytes()
    if len(data) < 12 or data[:4] != b"\xcf\xfa\xed\xfe":
        return None
    cpu_type = struct.unpack_from("<I", data, 4)[0]
    file_type = struct.unpack_from("<I", data, 12)[0]
    if cpu_type != 0x0100000C or file_type != 1:
        return None
    return {"format": "Mach-O 64-bit arm64 MH_OBJECT", "size_bytes": len(data), "sha256": digest(path)}


def normalized_source_hash(path: Path) -> str:
    text = path.read_text()
    text = text.replace('#include "WalleyeADTPolicy.h"', '#include "walleye_adt_policy.h"', 1)
    text = text.replace("\n#if defined(ARM64_BOARD_CONFIG_WALLEYE)\n", "", 1)
    text = text.replace("\n#endif /* ARM64_BOARD_CONFIG_WALLEYE */\n", "\n", 1)
    return hashlib.sha256(text.encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path,
                        help="existing full SWEET+M1+M3A XNU worktree")
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "walleye-m3d")
    args = parser.parse_args()
    source = args.source.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []

    source_sha = run(["git", "-C", str(source), "rev-parse", "HEAD"])
    source_commit = source_sha.stdout.strip() if source_sha.returncode == 0 else None
    if source_commit != XNU_COMMIT:
        errors.append("source is not pinned XNU commit")
    for relative in (SOURCE_LIST, "iokit/Kernel/arm/WalleyePlatformExpert.cpp"):
        if not (source / relative).is_file():
            errors.append(f"missing M1/M3A prerequisite: {relative}")

    apply_check = run(["git", "-C", str(source), "apply", "--check", str(PATCH)])
    if apply_check.returncode:
        errors.append("M3D patch does not apply cleanly after M1/M3A")

    compiler = compiler_path()
    compiler_version = None
    runs: list[dict[str, Any]] = []
    if compiler is None:
        errors.append("no compatible clang compiler available")
    else:
        compiler_version = run([compiler, "--version"]).stdout.splitlines()[0]

    staged: dict[str, Any] = {"patch_applied": False, "source_list_registered": False,
                               "header_unchanged": False, "implementation_semantically_unchanged": False}
    with tempfile.TemporaryDirectory(prefix="walleye-m3d-") as temp_name:
        stage = Path(temp_name)
        (stage / "iokit/conf").mkdir(parents=True)
        (stage / "iokit/Kernel/arm").mkdir(parents=True)
        shutil.copy2(source / SOURCE_LIST, stage / SOURCE_LIST)
        init = run(["git", "init", "-q"], stage)
        applied = run(["git", "apply", str(PATCH)], stage)
        staged["patch_applied"] = init.returncode == 0 and applied.returncode == 0
        staged_source = stage / XNU_SOURCE
        staged_header = stage / XNU_HEADER
        if staged["patch_applied"] and staged_source.is_file() and staged_header.is_file():
            staged["source_list_registered"] = XNU_SOURCE + "                              optional iokitcpp" in (stage / SOURCE_LIST).read_text()
            staged["header_unchanged"] = digest(staged_header) == digest(M3C_HEADER)
            staged["implementation_semantically_unchanged"] = normalized_source_hash(staged_source) == digest(M3C_SOURCE)
            if not all(staged.values()):
                errors.append("staged helper differs from M3C interface or implementation")
            if compiler is not None:
                for index in (1, 2):
                    object_path = out / f"arm64-run{index}" / "WalleyeADTPolicy.o"
                    object_path.parent.mkdir(parents=True, exist_ok=True)
                    command = [compiler, f"--target={TARGET}", *ARCH_FLAGS, "-DARM64_BOARD_CONFIG_WALLEYE", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic", "-ffreestanding", "-fno-builtin", "-fno-stack-protector", "-nostdinc", "-I", str(stage / "iokit/Kernel/arm"), "-c", str(staged_source), "-o", str(object_path)]
                    result = run(command)
                    info = macho_info(object_path) if result.returncode == 0 and object_path.is_file() else None
                    runs.append({"command": command, "returncode": result.returncode, "stderr": result.stderr, "object": info})
                    if result.returncode != 0 or info is None:
                        errors.append(f"actual XNU-path compile run {index} failed")
        else:
            errors.append("could not stage M3D patch in temporary XNU-path context")

    deterministic = len(runs) == 2 and all(run_data["object"] for run_data in runs) and runs[0]["object"]["sha256"] == runs[1]["object"]["sha256"]
    if runs and not deterministic:
        errors.append("actual XNU-path object builds were not byte-identical")
    result = {
        "schema_version": 1,
        "milestone": "M3D",
        "source": {"path": str(source), "xnu_commit": source_commit, "expected_xnu_commit": XNU_COMMIT},
        "patch": {"path": str(PATCH.relative_to(ROOT)), "sha256": digest(PATCH), "apply_check": "passed" if not apply_check.returncode else "failed"},
        "staging": staged,
        "compiler": {"path": compiler, "version": compiler_version, "target": TARGET, "architecture_flags": ARCH_FLAGS},
        "compilation": {"runs": runs, "byte_identical": deterministic, "linked": False, "kernel_built": False},
        "success": not errors,
        "errors": errors,
        "claims": {"runtime_call_site": False, "native_adt_parser": False, "kernel_linked": False, "kernel_built": False, "boot_ready": False},
    }
    (out / "build-result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
