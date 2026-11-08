#!/usr/bin/env python3
"""Strict offline validator for the versioned WALLEYE XNU boot contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

U64_LIMIT = 1 << 64
BOARD = ("Google Pixel 2", "walleye", "Qualcomm MSM8998", "arm64")
ORDER = [
    "entry-state",
    "boot-args-bounds",
    "memory-ownership",
    "adt-validation",
    "platform-expert",
    "gic-policy",
    "timer-policy",
    "primary-cpu",
    "secondary-cpus",
]
ALLOWED_EVIDENCE = {"project-target", "direct-source", "historical-report", "derived", "verified-measurement"}
FORBIDDEN_WALLEYE_VALUES = ("xiaomi,sweet", "qcom,kryo470", "sweet-fbcon", "/sweet-ufs", "0x9c000000")


def required(obj: Any, fields: tuple[str, ...] | list[str], path: str, errors: list[str]) -> bool:
    if not isinstance(obj, dict):
        errors.append(f"{path}: expected object")
        return False
    for field in fields:
        if field not in obj:
            errors.append(f"{path}/{field}: missing required field")
    return all(field in obj for field in fields)


def u64(value: Any, path: str, errors: list[str]) -> int | None:
    if isinstance(value, bool):
        errors.append(f"{path}: boolean is not an integer")
        return None
    if isinstance(value, str):
        if not value.startswith("0x"):
            errors.append(f"{path}: address/size strings must be hexadecimal")
            return None
        try:
            parsed = int(value, 16)
        except ValueError:
            errors.append(f"{path}: malformed hexadecimal integer")
            return None
    elif isinstance(value, int):
        parsed = value
    else:
        errors.append(f"{path}: expected integer or hexadecimal string")
        return None
    if parsed < 0 or parsed >= U64_LIMIT:
        errors.append(f"{path}: outside unsigned 64-bit range")
        return None
    return parsed


def checked_range(entry: Any, path: str, errors: list[str]) -> tuple[int, int] | None:
    if not required(entry, ["start", "size", "alignment"], path, errors):
        return None
    start = u64(entry["start"], path + "/start", errors)
    size = u64(entry["size"], path + "/size", errors)
    alignment = u64(entry["alignment"], path + "/alignment", errors)
    if start is None or size is None or alignment is None:
        return None
    if size == 0:
        errors.append(f"{path}/size: zero-sized range")
        return None
    if alignment == 0 or alignment & (alignment - 1):
        errors.append(f"{path}/alignment: must be a nonzero power of two")
        return None
    if start % alignment or size % alignment:
        errors.append(f"{path}: range violates declared alignment")
    end = start + size
    if end > U64_LIMIT:
        errors.append(f"{path}: start + size overflows unsigned 64-bit")
        return None
    return start, end


def wrapper(value: Any, path: str, provenance: dict[str, Any], errors: list[str], address: bool = False) -> Any:
    if not required(value, ["value", "status"], path, errors):
        return None
    actual, status = value["value"], value["status"]
    if status in ("guessed", "assumed", "inferred-unverified"):
        errors.append(f"{path}/status: guessed values are forbidden")
    if status == "unresolved":
        if actual is not None:
            errors.append(f"{path}: unresolved value must be null")
        return None
    if actual is None:
        errors.append(f"{path}: resolved status requires a value")
        return None
    if status not in ALLOWED_EVIDENCE:
        errors.append(f"{path}/status: unsupported evidence status")
    provenance_id = value.get("provenance")
    if not isinstance(provenance_id, str) or provenance_id not in provenance:
        errors.append(f"{path}/provenance: missing or unknown provenance")
    if address:
        u64(actual, path + "/value", errors)
    return actual


def overlaps(ranges: list[tuple[int, int, str]], label: str, errors: list[str]) -> None:
    ranges.sort()
    for previous, current in zip(ranges, ranges[1:]):
        if current[0] < previous[1]:
            errors.append(f"{label}: {previous[2]} overlaps {current[2]}")


def validate(data: dict[str, Any], platform: dict[str, Any] | None = None) -> tuple[str, list[str], list[str]]:
    errors: list[str] = []
    unresolved: list[str] = []
    top = [
        "schema_version", "contract", "board", "execution_state", "kernel_image", "boot_args",
        "physical_memory", "reserved_memory", "device_tree", "firmware_services",
        "interrupt_controller", "timer", "initialization_dependencies", "provenance",
        "unresolved_boot_critical",
    ]
    if not required(data, top, "", errors):
        return "invalid", errors, unresolved
    if data["schema_version"] != 1:
        errors.append("/schema_version: unsupported contract schema")

    contract = data["contract"]
    if required(contract, ["id", "version", "purpose", "boot_ready"], "/contract", errors):
        if contract["id"] != "ios-walleye-xnu-boot-information" or contract["version"] != 1:
            errors.append("/contract: unsupported identifier or version")
        if contract["boot_ready"] is not False:
            errors.append("/contract/boot_ready: offline contract must never claim readiness")

    provenance = data["provenance"] if isinstance(data["provenance"], dict) else {}
    if not provenance:
        errors.append("/provenance: expected non-empty provenance map")
    for name, record in provenance.items():
        path = f"/provenance/{name}"
        if required(record, ["status", "source"], path, errors):
            if record["status"] not in ALLOWED_EVIDENCE:
                errors.append(path + "/status: unsupported")
            if not isinstance(record["source"], str) or not record["source"].strip():
                errors.append(path + "/source: expected non-empty source")
            if "sha256" in record and (not isinstance(record["sha256"], str) or len(record["sha256"]) != 64):
                errors.append(path + "/sha256: expected 64 hexadecimal characters")

    board = data["board"]
    if required(board, ["device", "codename", "soc", "architecture", "provenance", "adt_identity"], "/board", errors):
        if (board["device"], board["codename"], board["soc"], board["architecture"]) != BOARD:
            errors.append("/board: invalid WALLEYE identity")
        if board["provenance"] not in provenance:
            errors.append("/board/provenance: unknown provenance")
        identity = board["adt_identity"]
        if required(identity, ["status", "root_compatible", "target_type", "model"], "/board/adt_identity", errors):
            if identity["status"] == "unresolved":
                if any(identity[key] is not None for key in ("root_compatible", "target_type", "model")):
                    errors.append("/board/adt_identity: unresolved identity values must be null")
                unresolved.append("ADT board identity")

    execution = data["execution_state"]
    execution_fields = ["initial_exception_level", "x0_boot_args_pointer", "mmu_state", "cache_state", "writable_bootstrap_tables"]
    if required(execution, ["aarch64_required", "entry_contract_provenance", *execution_fields], "/execution_state", errors):
        if execution["aarch64_required"] is not True:
            errors.append("/execution_state/aarch64_required: must be true")
        if execution["entry_contract_provenance"] not in provenance:
            errors.append("/execution_state/entry_contract_provenance: unknown")
        for field in execution_fields:
            value = wrapper(execution[field], f"/execution_state/{field}", provenance, errors, address=field == "x0_boot_args_pointer")
            if value is None:
                unresolved.append("execution state: " + field)

    image = data["kernel_image"]
    image_fields = ["physical_load_address", "physical_entry_address", "image_size", "linked_virtual_base"]
    if required(image, ["format_required", "architecture_required", "source_provenance", *image_fields], "/kernel_image", errors):
        if image["format_required"] != "mach-o64" or image["architecture_required"] != "arm64":
            errors.append("/kernel_image: expected plain ARM64 Mach-O 64")
        for field in image_fields:
            value = wrapper(image[field], f"/kernel_image/{field}", provenance, errors, address=True)
            if value is None:
                unresolved.append("kernel image: " + field)

    boot_args = data["boot_args"]
    boot_fields = ["virtBase", "physBase", "memSize", "topOfKernelData", "deviceTreeP", "deviceTreeLength", "commandLine", "bootFlags", "memSizeActual"]
    if required(boot_args, ["abi", "structure_revision_required", "structure_version_required", "structure_provenance", "pointer", "size_bytes", "fields", "video"], "/boot_args", errors):
        if boot_args["abi"] != "xnu-8796-arm64-boot_args" or boot_args["structure_revision_required"] != 2 or boot_args["structure_version_required"] != 2:
            errors.append("/boot_args: unsupported ABI revision/version")
        wrapper(boot_args["pointer"], "/boot_args/pointer", provenance, errors, address=True)
        wrapper(boot_args["size_bytes"], "/boot_args/size_bytes", provenance, errors, address=True)
        fields = boot_args["fields"]
        if required(fields, boot_fields, "/boot_args/fields", errors):
            for field in boot_fields:
                address = field not in ("commandLine",)
                if wrapper(fields[field], f"/boot_args/fields/{field}", provenance, errors, address=address) is None:
                    unresolved.append("boot_args: " + field)
        if not isinstance(boot_args["video"], dict) or boot_args["video"].get("status") != "unsupported":
            errors.append("/boot_args/video: M1 framebuffer path must remain unsupported")

    memory = data["physical_memory"]
    declared: list[tuple[int, int, str]] = []
    if required(memory, ["address_bits", "ownership_status", "regions", "loader_safe_ranges", "managed_ranges"], "/physical_memory", errors):
        if memory["address_bits"] != 64:
            errors.append("/physical_memory/address_bits: expected 64")
        if memory["ownership_status"] != "unresolved" or memory["loader_safe_ranges"] is not None or memory["managed_ranges"] is not None:
            errors.append("/physical_memory: loader/managed ownership must remain unresolved")
        regions = memory["regions"]
        if not isinstance(regions, list) or not regions:
            errors.append("/physical_memory/regions: expected evidence ranges")
        else:
            for index, region in enumerate(regions):
                path = f"/physical_memory/regions/{index}"
                if not required(region, ["id", "kind", "start", "size", "alignment", "status", "provenance"], path, errors):
                    continue
                result = checked_range(region, path, errors)
                if result:
                    declared.append((result[0], result[1], str(region["id"])))
                if region["status"] not in ALLOWED_EVIDENCE or region["provenance"] not in provenance:
                    errors.append(path + ": invalid evidence/provenance")
            overlaps(declared.copy(), "/physical_memory/regions", errors)
        unresolved.append("physical memory ownership")

    reserved = data["reserved_memory"]
    if required(reserved, ["inventory_status", "total_children", "static_children", "dynamic_children", "entries", "dynamic_placement_status", "provenance"], "/reserved_memory", errors):
        counts = (reserved["total_children"], reserved["static_children"], reserved["dynamic_children"])
        if counts != (20, 15, 5) or sum(counts[1:]) != counts[0]:
            errors.append("/reserved_memory: summary counts mismatch")
        if reserved["provenance"] not in provenance:
            errors.append("/reserved_memory/provenance: unknown")
        entries = reserved["entries"]
        placed: list[tuple[int, int, str]] = []
        if not isinstance(entries, list):
            errors.append("/reserved_memory/entries: expected list")
        else:
            for index, entry in enumerate(entries):
                path = f"/reserved_memory/entries/{index}"
                if not required(entry, ["id", "start", "size", "alignment", "status", "provenance"], path, errors):
                    continue
                result = checked_range(entry, path, errors)
                if result:
                    placed.append((result[0], result[1], str(entry["id"])))
                    if not any(result[0] >= start and result[1] <= end for start, end, _ in declared):
                        errors.append(path + ": reservation is outside declared RAM")
                if entry["status"] not in ALLOWED_EVIDENCE or entry["provenance"] not in provenance:
                    errors.append(path + ": invalid evidence/provenance")
            overlaps(placed, "/reserved_memory/entries", errors)
        if reserved["inventory_status"] != "complete" or reserved["dynamic_placement_status"] != "resolved" or len(entries) != 20:
            unresolved.append("reserved-memory inventory/placement")

    tree = data["device_tree"]
    if required(tree, ["handoff", "linux_source_evidence", "translation"], "/device_tree", errors):
        handoff = tree["handoff"]
        if required(handoff, ["format", "status", "pointer", "length", "provenance"], "/device_tree/handoff", errors):
            if handoff["format"] != "apple-device-tree-flat":
                errors.append("/device_tree/handoff/format: XNU requires Apple flattened device tree")
            if handoff["status"] == "unresolved" and (handoff["pointer"] is not None or handoff["length"] is not None):
                errors.append("/device_tree/handoff: unresolved pointer/length must be null")
            if handoff["provenance"] not in provenance:
                errors.append("/device_tree/handoff/provenance: unknown")
        linux = tree["linux_source_evidence"]
        if not isinstance(linux, dict) or linux.get("format") != "linux-fdt-v17":
            errors.append("/device_tree/linux_source_evidence/format: expected Linux FDT v17 evidence")
        translation = tree["translation"]
        if not isinstance(translation, dict) or translation.get("direct_reuse_permitted") is not False:
            errors.append("/device_tree/translation: direct FDT reuse must be forbidden")
        if not isinstance(translation, dict) or translation.get("status") != "resolved":
            unresolved.append("FDT-to-ADT translation")

    firmware = data["firmware_services"]
    if not isinstance(firmware, dict):
        errors.append("/firmware_services: expected object")
    else:
        for name in ("psci", "secure_monitor", "gic_ownership", "counter_access"):
            item = firmware.get(name)
            if not isinstance(item, dict) or item.get("status") != "unresolved":
                errors.append(f"/firmware_services/{name}: must remain explicitly unresolved")
            else:
                unresolved.append("firmware: " + name)

    gic = data["interrupt_controller"]
    if required(gic, ["type", "distributor", "redistributor", "security_state", "system_register_interface", "register_writes_permitted"], "/interrupt_controller", errors):
        wrapper(gic["type"], "/interrupt_controller/type", provenance, errors)
        wrapper(gic["distributor"].get("base"), "/interrupt_controller/distributor/base", provenance, errors, address=True)
        wrapper(gic["distributor"].get("size"), "/interrupt_controller/distributor/size", provenance, errors, address=True)
        wrapper(gic["redistributor"].get("base"), "/interrupt_controller/redistributor/base", provenance, errors, address=True)
        wrapper(gic["redistributor"].get("size"), "/interrupt_controller/redistributor/size", provenance, errors, address=True)
        wrapper(gic["redistributor"].get("stride"), "/interrupt_controller/redistributor/stride", provenance, errors, address=True)
        if gic["register_writes_permitted"] is not False or gic["security_state"] != "unresolved" or gic["system_register_interface"] != "unresolved":
            errors.append("/interrupt_controller: unknown policy must permit no writes")
        unresolved.append("GIC policy and complete ranges")

    timer = data["timer"]
    if required(timer, ["type", "intid", "counter_frequency_hz", "routing_state", "register_access", "enable_permitted"], "/timer", errors):
        intid = wrapper(timer["intid"], "/timer/intid", provenance, errors)
        if intid is not None and (not isinstance(intid, int) or isinstance(intid, bool) or not 16 <= intid <= 31):
            errors.append("/timer/intid: virtual timer must be a PPI")
        wrapper(timer["counter_frequency_hz"], "/timer/counter_frequency_hz", provenance, errors)
        if timer["routing_state"] != "unresolved" or timer["register_access"] != "unresolved" or timer["enable_permitted"] is not False:
            errors.append("/timer: unresolved route/access must keep timer disabled")
        unresolved.append("timer frequency/routing/access")

    dependencies = data["initialization_dependencies"]
    if not isinstance(dependencies, list) or [item.get("id") for item in dependencies if isinstance(item, dict)] != ORDER:
        errors.append("/initialization_dependencies: IDs/order mismatch")
    elif any(item.get("depends_on") != ([] if index == 0 else [ORDER[index - 1]]) for index, item in enumerate(dependencies)):
        errors.append("/initialization_dependencies: dependency chain mismatch")

    critical = data["unresolved_boot_critical"]
    if not isinstance(critical, list) or not critical or any(not isinstance(item, str) or not item for item in critical):
        errors.append("/unresolved_boot_critical: expected non-empty strings")
    else:
        unresolved.extend(critical)

    rendered = json.dumps(data).lower()
    for forbidden in FORBIDDEN_WALLEYE_VALUES:
        if forbidden.lower() in rendered:
            errors.append(f"/: SWEET-only value leaked into WALLEYE contract: {forbidden}")

    if platform is not None:
        try:
            region = data["physical_memory"]["regions"][0]
            if region["start"] != platform["memory"]["declaration"]["start"]:
                errors.append("/physical_memory/regions/0/start: differs from Phase 2B")
            expected_size = int(platform["memory"]["declaration"]["end_exclusive"], 16) - int(region["start"], 16)
            if int(region["size"], 16) != expected_size:
                errors.append("/physical_memory/regions/0/size: differs from Phase 2B")
            if data["reserved_memory"]["total_children"] != platform["reserved_memory"]["total_children"]:
                errors.append("/reserved_memory/total_children: differs from Phase 2B")
            if data["interrupt_controller"]["distributor"]["base"]["value"] != platform["interrupt_controller"]["distributor"]["base"]:
                errors.append("/interrupt_controller/distributor/base: differs from Phase 2B")
            if data["timer"]["intid"]["value"] != platform["timer"]["intid"]:
                errors.append("/timer/intid: differs from Phase 2B")
        except (KeyError, IndexError, TypeError, ValueError):
            errors.append("/: Phase 2B cross-validation could not resolve required fields")

    unique_unresolved = list(dict.fromkeys(unresolved))
    if errors:
        return "invalid", errors, unique_unresolved
    if unique_unresolved:
        return "valid_with_unresolved", [], unique_unresolved
    return "valid_offline", [], []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract", type=Path)
    args = parser.parse_args()
    try:
        data = json.loads(args.contract.read_text())
        platform = json.loads(args.contract.with_name("msm8998-platform.json").read_text())
    except (OSError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "invalid", "errors": [str(error)], "unresolved": []}, indent=2))
        return 1
    status, errors, unresolved = validate(data, platform)
    print(json.dumps({"status": status, "errors": errors, "unresolved": unresolved}, indent=2))
    return 1 if status == "invalid" else 0


if __name__ == "__main__":
    raise SystemExit(main())
