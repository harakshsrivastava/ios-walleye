#!/usr/bin/env python3
"""Reproducibly compile and host-test the pure WALLEYE ADT policy helper."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "include" / "walleye_adt_policy.h"
SOURCE = ROOT / "src" / "walleye_adt_policy.c"
HOST_TEST = ROOT / "tests" / "native" / "walleye_adt_policy_test.c"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_tool(candidates: list[str | None]) -> str | None:
    for candidate in candidates:
        if not candidate:
            continue
        if "/" in candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def run(
    command: list[str], log: list[str], *, cwd: Path = ROOT,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    log.append("$ " + shlex.join(command))
    result = subprocess.run(
        command, cwd=cwd, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    if result.stdout:
        log.append(result.stdout.rstrip())
    log.append(f"exit={result.returncode}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "walleye-m3c")
    args = parser.parse_args()
    out = args.out.resolve()
    arm1 = out / "arm64-run1"
    arm2 = out / "arm64-run2"
    host = out / "host"
    for directory in (arm1, arm2, host):
        directory.mkdir(parents=True, exist_ok=True)

    log: list[str] = []
    failures: list[str] = []
    clang = find_tool([
        os.environ.get("WALLEYE_CLANG"),
        "/workspace/toolchains/llvm19/usr/bin/clang-19",
        "clang-19", "clang",
    ])
    cc = find_tool([os.environ.get("CC"), "cc", "clang", "gcc"])
    if clang is None:
        failures.append("ARM64 Mach-O compiler unavailable")
    if cc is None:
        failures.append("host C compiler unavailable")

    clang_version = None
    host_version = None
    arm_objects: list[Path] = []
    arm_commands: list[str] = []
    clang_env = os.environ.copy()
    clang_env["SOURCE_DATE_EPOCH"] = "0"
    existing_ld = clang_env.get("LD_LIBRARY_PATH", "")
    local_ld = "/workspace/toolchains/llvm19/usr/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu"
    clang_env["LD_LIBRARY_PATH"] = local_ld + ((":" + existing_ld) if existing_ld else "")
    if clang:
        version = run([clang, "--version"], log, env=clang_env)
        clang_version = version.stdout.splitlines()[0] if version.stdout else None
        for index, directory in enumerate((arm1, arm2), start=1):
            obj = directory / "walleye_adt_policy.o"
            command = [
                clang, "--target=arm64-apple-darwin22",
                "-march=armv8-a", "-mno-outline-atomics",
                "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
                "-ffreestanding", "-fno-builtin", "-fno-stack-protector",
                "-nostdinc", "-I", str(ROOT / "include"),
                "-c", str(SOURCE), "-o", str(obj),
            ]
            arm_commands.append(shlex.join(command))
            result = run(command, log, env=clang_env)
            if result.returncode != 0:
                failures.append(f"ARM64 compile run {index} failed")
            elif obj.is_file():
                arm_objects.append(obj)

    reproducible = (
        len(arm_objects) == 2
        and arm_objects[0].read_bytes() == arm_objects[1].read_bytes()
    )
    if len(arm_objects) == 2 and not reproducible:
        failures.append("ARM64 objects are not byte-identical")

    macho: dict[str, Any] | None = None
    if arm_objects:
        inspected = run(
            [sys.executable, str(ROOT / "tools" / "inspect_macho.py"), str(arm_objects[0])],
            log,
        )
        if inspected.returncode == 0:
            try:
                macho = json.loads(inspected.stdout)
            except ValueError:
                failures.append("Mach-O inspector returned invalid JSON")
        else:
            failures.append("Mach-O inspection failed")
    if macho is not None:
        header = macho.get("header", {})
        if header.get("architecture") != "arm64" or header.get("filetype_name") != "MH_OBJECT":
            failures.append("output is not an ARM64 Mach-O MH_OBJECT")

    host_test_status = "unavailable"
    sanitizer_status = "unavailable"
    shared_status = "unavailable"
    host_command_text = None
    sanitizer_command_text = None
    shared_path = host / "libwalleye_adt_policy.so"
    if cc:
        version = run([cc, "--version"], log)
        host_version = version.stdout.splitlines()[0] if version.stdout else None
        common = [
            cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-I", str(ROOT / "include"), str(SOURCE), str(HOST_TEST),
        ]
        host_exe = host / "walleye_adt_policy_test"
        host_command = [*common, "-o", str(host_exe)]
        host_command_text = shlex.join(host_command)
        compiled = run(host_command, log)
        if compiled.returncode == 0:
            executed = run([str(host_exe)], log)
            host_test_status = "passed" if executed.returncode == 0 else "failed"
        else:
            host_test_status = "failed"
        if host_test_status == "failed":
            failures.append("host-native test failed")

        sanitizer_exe = host / "walleye_adt_policy_test_sanitized"
        sanitizer_command = [
            cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
            "-I", str(ROOT / "include"), str(SOURCE), str(HOST_TEST),
            "-o", str(sanitizer_exe),
        ]
        sanitizer_command_text = shlex.join(sanitizer_command)
        sanitized = run(sanitizer_command, log)
        if sanitized.returncode == 0:
            sanitizer_env = os.environ.copy()
            sanitizer_env["ASAN_OPTIONS"] = "detect_leaks=1"
            sanitizer_env["UBSAN_OPTIONS"] = "halt_on_error=1"
            executed = run([str(sanitizer_exe)], log, env=sanitizer_env)
            sanitizer_status = "passed" if executed.returncode == 0 else "failed"
            if sanitizer_status == "failed":
                failures.append("ASan/UBSan host test failed")

        shared_command = [
            cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-fPIC", "-shared", "-I", str(ROOT / "include"),
            str(SOURCE), "-o", str(shared_path),
        ]
        shared = run(shared_command, log)
        shared_status = "passed" if shared.returncode == 0 else "failed"
        if shared_status == "failed":
            failures.append("host shared-library build failed")

    object_record = None
    if arm_objects:
        object_record = {
            "path": str(arm_objects[0].relative_to(out)),
            "size_bytes": arm_objects[0].stat().st_size,
            "sha256": sha256(arm_objects[0]),
            "format": "Mach-O 64-bit arm64 MH_OBJECT" if macho else "unverified",
            "symbol": "_walleye_validate_normalized_adt",
        }
    result: dict[str, Any] = {
        "schema_version": 1,
        "milestone": "M3C",
        "inputs": {
            str(HEADER.relative_to(ROOT)): sha256(HEADER),
            str(SOURCE.relative_to(ROOT)): sha256(SOURCE),
            str(HOST_TEST.relative_to(ROOT)): sha256(HOST_TEST),
        },
        "toolchains": {
            "arm64_compiler": clang,
            "arm64_compiler_version": clang_version,
            "host_compiler": cc,
            "host_compiler_version": host_version,
        },
        "arm64_macho": {
            "target": "arm64-apple-darwin22",
            "architecture_flags": ["-march=armv8-a", "-mno-outline-atomics"],
            "commands": arm_commands,
            "runs": len(arm_objects),
            "byte_identical": reproducible,
            "object": object_record,
            "linked": False,
        },
        "host_validation": {
            "compile_command": host_command_text,
            "test_status": host_test_status,
            "sanitizer_command": sanitizer_command_text,
            "asan_ubsan_status": sanitizer_status,
            "differential_library_status": shared_status,
            "differential_library": str(shared_path.relative_to(out)) if shared_status == "passed" else None,
        },
        "success": not failures,
        "failures": failures,
        "claims": {
            "native_adt_parsed": False,
            "kernel_linked": False,
            "kernel_built": False,
            "runtime_integrated": False,
            "boot_ready": False,
        },
    }
    (out / "build-result.json").write_text(json.dumps(result, indent=2) + "\n")
    (out / "build.log").write_text("\n".join(log) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
