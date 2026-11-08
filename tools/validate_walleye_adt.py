#!/usr/bin/env python3
"""Validate bounded synthetic WALLEYE ADT registry fixtures.

This validates a JSON model only. It does not parse or produce native Apple
Device Tree bytes and does not establish runtime or boot compatibility.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "config" / "walleye-adt-policy.json"
STATUSES = ("valid_offline", "valid_with_unresolved", "invalid")


class DuplicateKeyError(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> tuple[dict[str, Any], int]:
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    if not isinstance(data, dict):
        raise ValueError("top-level JSON value must be an object")
    return data, len(raw)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version", "policy_id", "policy_version", "fixture_format",
        "scope", "native_binary_adt_parser", "boot_compatibility_claimed",
        "device_tree_contract", "identity_contract", "root_property_contract",
        "limits", "safe_nodes", "forbidden_node_prefixes",
        "forbidden_identity_fragments", "runtime_gates", "project_dependencies",
        "provenance", "unresolved",
    }
    missing = sorted(required - policy.keys())
    if missing:
        return [f"policy missing required fields: {', '.join(missing)}"]
    if policy["schema_version"] != 1 or policy["policy_version"] != 1:
        errors.append("unsupported policy schema or version")
    if policy["policy_id"] != "ios-walleye-adt-safe-nodes":
        errors.append("unexpected policy identifier")
    if policy["fixture_format"] != "walleye-synthetic-adt-registry-v1":
        errors.append("unsupported fixture format")
    if policy["scope"] != "offline-structural-validation-only":
        errors.append("policy scope must remain offline-only")
    if policy["native_binary_adt_parser"] is not False:
        errors.append("policy must not claim a native binary ADT parser")
    if policy["boot_compatibility_claimed"] is not False:
        errors.append("policy must not claim boot compatibility")
    tree_contract = policy["device_tree_contract"]
    if tree_contract != {
        "required_native_format": "apple-device-tree-flat",
        "validator_input_format": "walleye-synthetic-adt-registry-v1",
        "production_producer": None,
        "production_producer_status": "unresolved",
        "linux_fdt_direct_reuse": False,
    }:
        errors.append("native format/producer boundary drift")

    identity = policy["identity_contract"]
    physical = identity.get("physical_board", {})
    expected_board = {
        "manufacturer": "Google", "product": "Pixel 2",
        "codename": "walleye", "soc": "MSM8998",
        "status": "verified-historical-evidence",
        "provenance": "phase2b-platform-identity",
    }
    if physical != expected_board:
        errors.append("physical board identity or provenance drift")
    adt = identity.get("adt_root", {})
    if (
        adt.get("status") != "unresolved"
        or adt.get("match_property") is not None
        or adt.get("match_value") is not None
        or adt.get("producer") is not None
        or adt.get("producer_status") != "unresolved"
        or adt.get("android_identity_is_adt_identity") is not False
    ):
        errors.append("final ADT identity and producer must remain unresolved")
    if identity.get("identity_properties_allowed_while_unresolved") is not False:
        errors.append("unresolved identity properties must remain disallowed")
    if set(identity.get("inspected_xnu_match_properties", [])) != {
        "name", "compatible", "device_type", "model"
    }:
        errors.append("XNU match-property inventory drift")
    if policy["root_property_contract"] != {
        "required": ["name"],
        "optional": [],
        "identity_bearing_unresolved": [
            "compatible", "device_type", "model", "target-type"
        ],
        "unknown_property_policy": "reject",
    }:
        errors.append("root property contract drift")

    limits = policy["limits"]
    expected_limits = {
        "maximum_node_count": 2,
        "maximum_tree_depth": 1,
        "maximum_properties_per_node": 4,
        "maximum_property_size_bytes": 64,
        "maximum_fixture_size_bytes": 4096,
    }
    if limits != expected_limits:
        errors.append("policy bounds must not expand without a policy revision")

    safe_nodes = policy["safe_nodes"]
    if not isinstance(safe_nodes, list):
        errors.append("safe_nodes must be a list")
    else:
        paths = [node.get("path") for node in safe_nodes if isinstance(node, dict)]
        if paths != ["/", "/chosen"] or len(paths) != len(set(paths)):
            errors.append("v1 safe-node paths must be exactly / and /chosen")
        for node in safe_nodes:
            if not isinstance(node, dict):
                errors.append("safe-node entry must be an object")
                continue
            if node.get("publishes_iokit_nub") is not False:
                errors.append(f"{node.get('path')}: IOKit publication must remain false")
            allowed = node.get("allowed_properties", {})
            if set(allowed) != {"name"}:
                errors.append(f"{node.get('path')}: only structural name is allowed")

    if any(value is not False for value in policy["runtime_gates"].values()):
        errors.append("every runtime gate must remain false")
    if not isinstance(policy["unresolved"], list) or not policy["unresolved"]:
        errors.append("policy must retain explicit unresolved requirements")

    provenance = policy["provenance"]
    for source in (
        "phase2b-platform-identity", "xnu-pe-init-root-lookup",
        "xnu-pe-init-chosen-lookup", "xnu-root-matching", "m3a-fail-closed",
    ):
        if source not in provenance:
            errors.append(f"missing policy provenance: {source}")
    return errors


def project_consistency(policy: dict[str, Any], root: Path = ROOT) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    unresolved: list[str] = []
    deps = policy["project_dependencies"]
    try:
        boot = json.loads((root / deps["boot_contract"]).read_text())
        platform = json.loads((root / deps["platform_descriptor"]).read_text())
        expert = json.loads((root / deps["platform_expert"]).read_text())
        plan = json.loads((root / deps["port_plan"]).read_text())
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return [f"project dependency load failed: {exc}"], unresolved

    boot_validator = _load_module(
        "m3b_boot_contract_validator", root / "tools" / "validate_walleye_boot_contract.py"
    )
    status, boot_errors, boot_unresolved = boot_validator.validate(boot, platform)
    if status != deps["m2_required_status"] or boot_errors:
        errors.append("M2 boot contract status drift")
    if len(boot_unresolved) != deps["m2_required_unresolved_count"]:
        errors.append("M2 unresolved-item count drift")
    unresolved.extend(f"M2: {item}" for item in boot_unresolved)

    platform_info = platform.get("platform", {})
    if platform_info.get("device") != "Google Pixel 2":
        errors.append("Phase 2B device identity drift")
    if platform_info.get("codename") != "walleye":
        errors.append("Phase 2B codename drift")
    if platform_info.get("soc") != "Qualcomm MSM8998":
        errors.append("Phase 2B SoC identity drift")

    integration = expert.get("source_integration", {})
    behavior = expert.get("behavior", {})
    if integration.get("runtime_match_enabled") is not deps["m3a_required_match_enabled"]:
        errors.append("M3A runtime match gate drift")
    if behavior.get("start_supported") is not deps["m3a_required_start_supported"]:
        errors.append("M3A startup gate drift")
    if behavior.get("adt_node_publication") != deps["m3a_required_node_publication"]:
        errors.append("M3A node-publication gate drift")
    if integration.get("io_name_match") != "__walleye_m3a_disabled__":
        errors.append("M3A disabled sentinel drift")
    if behavior.get("firmware_calls") is not False:
        errors.append("M3A firmware calls must remain disabled")

    m3 = next((item for item in plan.get("roadmap", []) if item.get("id") == "M3"), {})
    if m3.get("status") != "m3b-completed-offline-validation":
        errors.append("port plan no longer records completed offline-only M3B")
    if plan.get("boot_readiness_claimed") is not False:
        errors.append("port plan must not claim boot readiness")
    return errors, unresolved


def _property_size(prop_type: str, value: Any) -> int | None:
    if prop_type == "string" and isinstance(value, str):
        return len(value.encode("utf-8")) + 1
    if prop_type == "string-list" and isinstance(value, list) and all(isinstance(v, str) for v in value):
        return sum(len(v.encode("utf-8")) + 1 for v in value)
    if prop_type == "uint32" and isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 0xffffffff:
        return 4
    if prop_type == "uint64" and isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 0xffffffffffffffff:
        return 8
    if prop_type == "boolean" and isinstance(value, bool):
        return 1
    return None


def validate_fixture(
    fixture: dict[str, Any], policy: dict[str, Any], root: Path = ROOT,
    raw_size: int | None = None,
) -> tuple[str, list[str], list[str]]:
    errors = validate_policy(policy)
    project_errors, project_unresolved = project_consistency(policy, root)
    errors.extend(project_errors)
    unresolved = list(policy.get("unresolved", [])) + project_unresolved

    required = {"fixture_format", "policy_version", "producer", "identity", "runtime", "tree"}
    missing = sorted(required - fixture.keys())
    extra = sorted(fixture.keys() - required)
    if missing:
        errors.append(f"fixture missing required fields: {', '.join(missing)}")
    if extra:
        errors.append(f"fixture has unsupported fields: {', '.join(extra)}")
    if missing:
        return "invalid", errors, sorted(set(unresolved))

    if fixture["fixture_format"] != policy["fixture_format"]:
        errors.append("fixture format mismatch")
    if fixture["policy_version"] != policy["policy_version"]:
        errors.append("unsupported fixture policy version")
    if raw_size is None:
        raw_size = len(json.dumps(fixture, separators=(",", ":")).encode("utf-8"))
    if raw_size > policy["limits"]["maximum_fixture_size_bytes"]:
        errors.append("fixture exceeds maximum byte size")

    producer = fixture["producer"]
    if producer != {
        "kind": "synthetic-test-fixture",
        "status": "test-only",
        "provenance": "config/walleye-adt-policy.json",
    }:
        errors.append("fixture producer must be explicit, synthetic, and test-only")

    identity = fixture["identity"]
    expected_physical = policy["identity_contract"]["physical_board"]
    if not isinstance(identity, dict) or identity.get("physical_board") != expected_physical:
        errors.append("fixture physical board identity or provenance mismatch")
    adt = identity.get("adt_root", {}) if isinstance(identity, dict) else {}
    expected_adt = {
        "status": "unresolved", "match_property": None, "match_value": None,
        "producer": None, "producer_status": "unresolved",
    }
    if adt != expected_adt:
        errors.append("fixture ADT identity conflicts with unresolved policy")

    if fixture["runtime"] != policy["runtime_gates"]:
        errors.append("fixture runtime gates must exactly match the all-disabled policy")

    rendered = json.dumps(fixture, sort_keys=True).lower()
    for fragment in policy["forbidden_identity_fragments"]:
        if fragment.lower() in rendered:
            errors.append(f"forbidden SWEET identity fragment: {fragment}")

    allowed_nodes = {entry["path"]: entry for entry in policy["safe_nodes"]}
    forbidden_prefixes = tuple(policy["forbidden_node_prefixes"])
    limits = policy["limits"]
    seen_paths: set[str] = set()
    node_count = 0
    identity_names = {"compatible", "model", "target-type", "device_type"}

    def visit(node: Any, parent_path: str | None, depth: int) -> None:
        nonlocal node_count
        if not isinstance(node, dict):
            errors.append("tree node must be an object")
            return
        if depth > limits["maximum_tree_depth"]:
            errors.append("tree exceeds maximum depth")
            return
        required_node = {"path", "node_type", "properties", "children"}
        if set(node) != required_node:
            errors.append("tree node fields must be exactly path, node_type, properties, children")
            return
        path = node["path"]
        if not isinstance(path, str) or not path.startswith("/"):
            errors.append("node path must be an absolute string")
            return
        node_count += 1
        if node_count > limits["maximum_node_count"]:
            errors.append("tree exceeds maximum node count")
        if path in seen_paths:
            errors.append(f"duplicate node path: {path}")
        seen_paths.add(path)
        if any(path == prefix or path.startswith(prefix + "/") for prefix in forbidden_prefixes):
            errors.append(f"unsupported hardware or operational node: {path}")
        rule = allowed_nodes.get(path)
        if rule is None:
            errors.append(f"unknown node path: {path}")
        if parent_path is None:
            if path != "/":
                errors.append("tree root path must be /")
        else:
            expected_parent = str(PurePosixPath(path).parent)
            if expected_parent != parent_path:
                errors.append(f"node parent/path mismatch: {path}")
            parent_rule = allowed_nodes.get(parent_path, {})
            if path not in parent_rule.get("allowed_children", []):
                errors.append(f"child not allowed by parent policy: {path}")
        if rule is not None and node["node_type"] != rule["node_type"]:
            errors.append(f"invalid node type for {path}")

        properties = node["properties"]
        if not isinstance(properties, list):
            errors.append(f"{path}: properties must be a list")
            properties = []
        if len(properties) > limits["maximum_properties_per_node"]:
            errors.append(f"{path}: too many properties")
        seen_properties: set[str] = set()
        for prop in properties:
            if not isinstance(prop, dict) or set(prop) != {"name", "type", "value", "provenance"}:
                errors.append(f"{path}: malformed property entry")
                continue
            name = prop["name"]
            if not isinstance(name, str):
                errors.append(f"{path}: property name must be a string")
                continue
            if name in seen_properties:
                errors.append(f"{path}: duplicate property: {name}")
            seen_properties.add(name)
            if path == "/" and name in identity_names:
                errors.append(f"unresolved ADT identity property is not allowed: {name}")
            prop_rule = rule.get("allowed_properties", {}).get(name) if rule else None
            if prop_rule is None:
                errors.append(f"{path}: property not allowed: {name}")
                continue
            if prop["type"] != prop_rule["type"]:
                errors.append(f"{path}/{name}: invalid property type")
            size = _property_size(prop["type"], prop["value"])
            if size is None:
                errors.append(f"{path}/{name}: value does not match declared type")
            elif size > limits["maximum_property_size_bytes"]:
                errors.append(f"{path}/{name}: property exceeds maximum size")
            if "constant" in prop_rule and prop["value"] != prop_rule["constant"]:
                errors.append(f"{path}/{name}: property value conflicts with policy")
            if prop["provenance"] != prop_rule["provenance"]:
                errors.append(f"{path}/{name}: missing or invalid provenance")
            if prop["provenance"] not in policy["provenance"]:
                errors.append(f"{path}/{name}: unknown provenance identifier")
        if rule is not None:
            missing_props = set(rule["required_properties"]) - seen_properties
            if missing_props:
                errors.append(f"{path}: missing required properties: {', '.join(sorted(missing_props))}")

        children = node["children"]
        if not isinstance(children, list):
            errors.append(f"{path}: children must be a list")
            return
        for child in children:
            visit(child, path, depth + 1)

    visit(fixture["tree"], None, 0)
    if errors:
        return "invalid", errors, sorted(set(unresolved))
    if unresolved:
        return "valid_with_unresolved", [], sorted(set(unresolved))
    return "valid_offline", [], []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    args = parser.parse_args()
    try:
        policy, _ = load_json(args.policy)
        fixture, raw_size = load_json(args.fixture)
        status, errors, unresolved = validate_fixture(fixture, policy, ROOT, raw_size)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
        status, errors, unresolved = "invalid", [str(exc)], []
    result = {"status": status, "errors": errors, "unresolved": unresolved}
    print(json.dumps(result, indent=2))
    return 0 if status != "invalid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
