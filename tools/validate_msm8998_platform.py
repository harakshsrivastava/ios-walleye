#!/usr/bin/env python3
"""Strict host-side validator for the offline MSM8998 platform descriptor."""

import argparse
import json
from pathlib import Path

MAX_U64 = (1 << 64) - 1
PROVENANCE_PATHS = (
    "/platform/device", "/platform/codename", "/platform/soc",
    "/cpu/architecture", "/cpu/count", "/interrupt_controller/type",
    "/interrupt_controller/distributor/base", "/interrupt_controller/redistributor/base",
    "/interrupt_controller/redistributor/stride", "/timer/type", "/timer/intid",
    "/timer/interrupt_class", "/memory/declaration/start", "/memory/declaration/end_exclusive",
    "/reserved_memory/total_children", "/reserved_memory/static_children",
    "/reserved_memory/dynamic_children", "/storage/ufs_controller/base",
    "/storage/ufs_controller/size", "/storage/ufs_phy/base",
    "/boot_interface/active_android_slot", "/boot_interface/active_dtbo_index_observed",
)


def _need(mapping, keys, path, errors):
    if not isinstance(mapping, dict):
        errors.append(f"{path}: expected object")
        return False
    missing = [key for key in keys if key not in mapping]
    errors.extend(f"{path}/{key}: missing required property" for key in missing)
    return not missing


def _u64(value, path, errors, allow_null=False):
    if value is None and allow_null: return None
    if isinstance(value, bool):
        errors.append(f"{path}: boolean is not an integer")
        return None
    try:
        number = int(value, 0) if isinstance(value, str) else value
    except (TypeError, ValueError):
        errors.append(f"{path}: expected integer or integer string")
        return None
    if not isinstance(number, int) or number < 0 or number > MAX_U64:
        errors.append(f"{path}: outside unsigned 64-bit range")
        return None
    return number


def _aligned(value, alignment, path, errors):
    if value is not None and value % alignment:
        errors.append(f"{path}: {value:#x} is not aligned to {alignment:#x}")


def _overlaps(ranges, label, errors):
    ordered = sorted(ranges)
    for left, right in zip(ordered, ordered[1:]):
        if right[0] < left[1]:
            errors.append(f"{label}: {left[2]} overlaps {right[2]}")


def validate(data):
    errors, unresolved = [], []
    if not _need(data, ("schema_version", "platform", "cpu", "interrupt_controller", "timer", "diagnostics",
                        "memory", "reserved_memory", "storage", "firmware", "boot_interface", "provenance"), "", errors):
        return {"status":"invalid", "errors":errors, "unresolved":unresolved}
    if data["schema_version"] != 1: errors.append("/schema_version: unsupported version")
    platform = data["platform"]
    if _need(platform, ("device", "codename", "soc", "purpose"), "/platform", errors):
        if platform["device"] != "Google Pixel 2" or platform["codename"] != "walleye" or platform["soc"] != "Qualcomm MSM8998":
            errors.append("/platform: descriptor identity is not the supported walleye/MSM8998 target")

    cpu = data["cpu"]
    if _need(cpu, ("architecture", "count", "topology_status", "boot_cpu_mpidr", "clusters", "cpus"), "/cpu", errors):
        count = _u64(cpu["count"], "/cpu/count", errors)
        if cpu["architecture"] != "arm64": errors.append("/cpu/architecture: only arm64 is supported")
        if not count or count > 256: errors.append("/cpu/count: must be between 1 and 256")
        if cpu["topology_status"] == "unknown":
            if cpu["cpus"] is not None or cpu["clusters"] is not None or cpu["boot_cpu_mpidr"] is not None:
                errors.append("/cpu: unknown topology must not contain guessed topology values")
            unresolved.append("cpu topology and boot MPIDR")
        elif cpu["topology_status"] == "resolved":
            if not isinstance(cpu["clusters"], list) or not cpu["clusters"]:
                errors.append("/cpu/clusters: resolved topology requires at least one cluster")
            if not isinstance(cpu["cpus"], list) or len(cpu["cpus"]) != count:
                errors.append("/cpu/cpus: resolved topology must contain exactly count entries")
            else:
                ids, mpidrs, boots = [], [], 0
                for i, entry in enumerate(cpu["cpus"]):
                    p = f"/cpu/cpus/{i}"
                    if not _need(entry, ("logical_id", "mpidr", "cluster_id", "boot"), p, errors): continue
                    ids.append(_u64(entry["logical_id"], p+"/logical_id", errors))
                    mpidrs.append(_u64(entry["mpidr"], p+"/mpidr", errors))
                    if not isinstance(entry["boot"], bool): errors.append(p+"/boot: expected boolean")
                    boots += entry["boot"] is True
                if ids != list(range(count)): errors.append("/cpu/cpus: logical IDs must be contiguous and ordered")
                if None not in mpidrs and len(set(mpidrs)) != len(mpidrs): errors.append("/cpu/cpus: duplicate MPIDR")
                if boots != 1: errors.append("/cpu/cpus: exactly one boot CPU is required")
                if isinstance(cpu["clusters"], list):
                    cluster_ids = [entry.get("id") for entry in cpu["clusters"] if isinstance(entry, dict)]
                    used_ids = [entry.get("cluster_id") for entry in cpu["cpus"] if isinstance(entry, dict)]
                    if len(cluster_ids) != len(set(cluster_ids)) or any(cid not in cluster_ids for cid in used_ids):
                        errors.append("/cpu/clusters: IDs must be unique and cover every CPU")
        else: errors.append("/cpu/topology_status: expected unknown or resolved")

    gic = data["interrupt_controller"]
    if _need(gic, ("type", "distributor", "redistributor", "security_state", "system_register_interface"), "/interrupt_controller", errors):
        if gic["type"] != "gicv3": errors.append("/interrupt_controller/type: only gicv3 is supported")
        if _need(gic["distributor"], ("base", "size"), "/interrupt_controller/distributor", errors):
            gicd = _u64(gic["distributor"]["base"], "/interrupt_controller/distributor/base", errors); _aligned(gicd, 0x10000, "/interrupt_controller/distributor/base", errors)
            if gic["distributor"]["size"] is None: unresolved.append("GIC distributor region size")
        if _need(gic["redistributor"], ("base", "size", "stride"), "/interrupt_controller/redistributor", errors):
            gicr = _u64(gic["redistributor"]["base"], "/interrupt_controller/redistributor/base", errors); _aligned(gicr, 0x10000, "/interrupt_controller/redistributor/base", errors)
            stride = _u64(gic["redistributor"]["stride"], "/interrupt_controller/redistributor/stride", errors)
            if stride is not None and (stride < 0x20000 or stride & (stride - 1)): errors.append("/interrupt_controller/redistributor/stride: unsupported GICv3 stride")
            if gic["redistributor"]["size"] is None: unresolved.append("GIC redistributor region size")
        if gic.get("security_state") == "unknown": unresolved.append("GIC interrupt security ownership")
        if gic.get("system_register_interface") == "unknown": unresolved.append("GIC system-register interface availability")

    timer = data["timer"]
    if _need(timer, ("type", "intid", "interrupt_class", "counter_frequency_hz", "routing_state"), "/timer", errors):
        intid = _u64(timer["intid"], "/timer/intid", errors)
        if timer["type"] != "arm-architected-virtual": errors.append("/timer/type: unsupported timer")
        if intid is not None and not 16 <= intid <= 31: errors.append("/timer/intid: virtual timer must use a PPI (16..31)")
        if timer["interrupt_class"] != "ppi": errors.append("/timer/interrupt_class: expected ppi")
        if timer["counter_frequency_hz"] is None: unresolved.append("architectural counter frequency")
        if timer["routing_state"] == "unknown": unresolved.append("virtual timer routing state")

    diagnostics = data["diagnostics"]
    if _need(diagnostics, ("uart", "framebuffer"), "/diagnostics", errors):
        for name in ("uart", "framebuffer"):
            item = diagnostics[name]
            expected = ("status", "type", "base", "clock_hz") if name == "uart" else ("status", "base")
            if not _need(item, expected, f"/diagnostics/{name}", errors): continue
            if item["status"] not in ("unknown", "resolved"): errors.append(f"/diagnostics/{name}/status: expected unknown or resolved")
            elif item["status"] == "unknown":
                if any(value is not None for key, value in item.items() if key != "status"):
                    errors.append(f"/diagnostics/{name}: unknown status must not include guessed values")
                unresolved.append(f"{name} diagnostic interface")

    memory = data["memory"]
    memory_start = memory_end = None
    if _need(memory, ("declaration", "loader_safe_ranges", "loader_safety_status"), "/memory", errors) and _need(memory["declaration"], ("start", "end_exclusive"), "/memory/declaration", errors):
        memory_start = _u64(memory["declaration"]["start"], "/memory/declaration/start", errors)
        memory_end = _u64(memory["declaration"]["end_exclusive"], "/memory/declaration/end_exclusive", errors)
        _aligned(memory_start, 0x1000, "/memory/declaration/start", errors); _aligned(memory_end, 0x1000, "/memory/declaration/end_exclusive", errors)
        if memory_start is not None and memory_end is not None and memory_end <= memory_start: errors.append("/memory/declaration: empty, reversed, or overflowing range")
        if memory["loader_safety_status"] == "unknown" and memory["loader_safe_ranges"] is not None: errors.append("/memory: unknown loader safety must not include guessed safe ranges")
        if memory["loader_safety_status"] == "unknown": unresolved.append("safe loader ranges")

    reserved = data["reserved_memory"]
    if _need(reserved, ("inventory_status", "total_children", "static_children", "dynamic_children", "entries", "dynamic_placement_status"), "/reserved_memory", errors):
        total = _u64(reserved["total_children"], "/reserved_memory/total_children", errors)
        static = _u64(reserved["static_children"], "/reserved_memory/static_children", errors)
        dynamic = _u64(reserved["dynamic_children"], "/reserved_memory/dynamic_children", errors)
        if None not in (total, static, dynamic) and static + dynamic != total: errors.append("/reserved_memory: static + dynamic must equal total")
        if not isinstance(reserved["entries"], list): errors.append("/reserved_memory/entries: expected array")
        else:
            if reserved["inventory_status"] == "complete" and total is not None and len(reserved["entries"]) != total:
                errors.append("/reserved_memory/entries: complete inventory must contain total_children entries")
            if total is not None and len(reserved["entries"]) > total:
                errors.append("/reserved_memory/entries: more entries than total_children")
            resolved_ranges = []
            for i, entry in enumerate(reserved["entries"]):
                p = f"/reserved_memory/entries/{i}"
                if not _need(entry, ("name", "kind", "status", "start", "end_exclusive"), p, errors): continue
                if entry["status"] == "unresolved":
                    if entry["start"] is not None or entry["end_exclusive"] is not None: errors.append(p+": unresolved entry must not have an address")
                    unresolved.append(f"reserved-memory placement: {entry['name']}")
                    continue
                start = _u64(entry["start"], p+"/start", errors); end = _u64(entry["end_exclusive"], p+"/end_exclusive", errors)
                _aligned(start, 0x1000, p+"/start", errors); _aligned(end, 0x1000, p+"/end_exclusive", errors)
                if start is not None and end is not None:
                    if end <= start: errors.append(p+": empty, reversed, or overflowing range")
                    elif memory_start is not None and (start < memory_start or end > memory_end): errors.append(p+": range is outside declared memory")
                    else: resolved_ranges.append((start, end, entry["name"]))
            _overlaps(resolved_ranges, "/reserved_memory/entries", errors)
        if reserved["inventory_status"] == "summary-only": unresolved.append("15 static reserved-memory ranges absent from surviving evidence")
        if dynamic and reserved["dynamic_placement_status"] == "unresolved": unresolved.append(f"{dynamic} dynamic reserved-memory placements")

    storage = data["storage"]
    if _need(storage, ("ufs_controller", "ufs_phy", "firmware_link_state", "clock_reset_state"), "/storage", errors):
        mmio = []
        for name in ("ufs_controller", "ufs_phy"):
            region = storage[name]; p = f"/storage/{name}"
            if not _need(region, ("base", "size"), p, errors): continue
            base = _u64(region["base"], p+"/base", errors); _aligned(base, 0x1000, p+"/base", errors)
            size = _u64(region["size"], p+"/size", errors, allow_null=True)
            if size is None: unresolved.append(f"{name} region size")
            elif size == 0: errors.append(p+"/size: must be non-zero")
            elif base is not None:
                if base > MAX_U64 - size: errors.append(p+": address overflow")
                else: mmio.append((base, base + size, name))
        _overlaps(mmio, "/storage", errors)
        if storage["firmware_link_state"] == "unknown": unresolved.append("UFS firmware link state")
        if storage["clock_reset_state"] == "unknown": unresolved.append("UFS clock/reset state")

    firmware = data["firmware"]
    if _need(firmware, ("initial_exception_level", "psci_version", "psci_conduit", "cpu_on_supported", "secure_monitor_contract", "gic_security_ownership", "status"), "/firmware", errors):
        if firmware["status"] == "unknown":
            if any(firmware[key] is not None for key in firmware if key != "status"): errors.append("/firmware: unknown status must not contain guessed values")
            unresolved.append("firmware, PSCI, exception-level, and secure-monitor contracts")

    boot = data["boot_interface"]
    if _need(boot, ("active_android_slot", "active_dtbo_index_observed", "apple_boot_args_layout", "fdt_to_adt_contract", "bootloader_time_equivalence"), "/boot_interface", errors):
        index = _u64(boot["active_dtbo_index_observed"], "/boot_interface/active_dtbo_index_observed", errors)
        if index is not None and index > 4095: errors.append("/boot_interface/active_dtbo_index_observed: unreasonable index")
        if boot["bootloader_time_equivalence"] == "unknown": unresolved.append("runtime-FDT versus bootloader-time equivalence")
        if boot["apple_boot_args_layout"] is None: unresolved.append("Apple boot-arguments layout")
        if boot["fdt_to_adt_contract"] is None: unresolved.append("FDT-to-ADT translation contract")

    provenance = data["provenance"]
    if isinstance(provenance, dict):
        for path in PROVENANCE_PATHS:
            record = provenance.get(path)
            if not isinstance(record, dict) or not record.get("status") or not record.get("source"):
                errors.append(f"/provenance: missing complete record for {path}")
    else: errors.append("/provenance: expected object")

    return {"status":"invalid" if errors else ("valid_with_unresolved" if unresolved else "valid"),
            "errors":errors, "unresolved":sorted(set(unresolved))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("descriptor", type=Path)
    args = parser.parse_args()
    try: data = json.loads(args.descriptor.read_text())
    except (OSError, json.JSONDecodeError) as error:
        print(json.dumps({"status":"invalid", "errors":[str(error)], "unresolved":[]}, indent=2)); raise SystemExit(1)
    result = validate(data); print(json.dumps(result, indent=2))
    raise SystemExit(bool(result["errors"]))


if __name__ == "__main__": main()
