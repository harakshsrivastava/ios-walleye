#!/usr/bin/env python3
"""Validate a SWEET reference kernel against the committed provenance contract."""

import argparse
import importlib.util
import json
from pathlib import Path


def validate(report, reference):
    errors = []
    expected = reference["kernel"]
    checks = {
        "sha256": report["sha256"],
        "size_bytes": report["size"],
        "architecture": report["header"]["architecture"],
        "filetype": report["header"]["filetype_name"],
        "entry_kind": (report["entry"] or {}).get("kind"),
        "entry_symbol": (report["entry"] or {}).get("nearest_symbol"),
    }
    for key, actual in checks.items():
        if actual != expected[key]: errors.append(f"{key}: expected {expected[key]!r}, got {actual!r}")
    if report["fixups"] != expected["dyld_fixups"]:
        errors.append("dyld_fixups differ")
    if report["relocations"] != expected["relocations"]:
        errors.append("relocations differ")
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("kernel", type=Path)
    parser.add_argument("--reference", type=Path, default=Path("config/sweet-kernel-reference.json"))
    args = parser.parse_args()
    script = Path(__file__).with_name("inspect_macho.py")
    spec = importlib.util.spec_from_file_location("inspect_macho", script)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    errors = validate(module.inspect(args.kernel), json.loads(args.reference.read_text()))
    if errors:
        for error in errors: print(error)
        raise SystemExit(1)
    print("SWEET reference kernel matches committed provenance contract")


if __name__ == "__main__": main()
