#!/usr/bin/env python3
"""Validate the machine-readable minimal XNU/MSM8998 port architecture plan."""

import argparse
import json
from pathlib import Path

EXPECTED_COMMITS = {
    "recovery_commit": "9c82853fb25d8b0a2483340a39941f678c335c87",
    "phase_2a_commit": "376619fa7347874d0f31787ea23044743ce394f4",
    "phase_2b_commit": "2355504cfa1bb53bbaedeb0068b55b206084f0fe",
}
CATEGORIES = {"directly-reusable", "reusable-with-configuration-changes", "reusable-with-source-modifications", "sweet-specific-replace", "blocked-missing-evidence"}
INSPECTIONS = {"direct-baseline-source", "direct-patched-source", "unresolved-mapping"}
STAGE_IDS = ["firmware-contract", "cpu-state", "memory-contract", "early-diagnostics", "platform-expert", "gic", "timer", "primary-cpu", "secondary-cpus"]
MAP_FIELDS = ("id", "domain", "source_path", "symbols", "inspection", "sweet_behavior", "walleye_requirement", "evidence", "dependencies", "missing", "validation")
STAGE_FIELDS = ("order", "id", "name", "preconditions", "inputs", "outputs", "failure_conditions", "firmware_services", "offline_invariants", "hardware_dependencies")
MILESTONE_FIELDS = ("id", "objective", "components", "dependencies", "offline_tests", "acceptance", "blockers", "complexity")


def _required(obj, fields, path, errors):
    if not isinstance(obj, dict):
        errors.append(f"{path}: expected object"); return False
    for field in fields:
        if field not in obj: errors.append(f"{path}/{field}: missing required property")
    return all(field in obj for field in fields)


def _nonempty_list(value, path, errors, allow_empty=False):
    if not isinstance(value, list) or (not allow_empty and not value): errors.append(f"{path}: expected {'a list' if allow_empty else 'a non-empty list'}")


def _pointer(document, pointer):
    value = document
    for token in pointer.lstrip("/").split("/") if pointer else []:
        value = value[token.replace("~1", "/").replace("~0", "~")]
    return value


def validate(data, platform=None):
    errors = []
    top = ("schema_version", "plan_id", "boot_readiness_claimed", "integration", "source_baseline", "hardware_claims", "inspected_source_paths", "source_map", "initialization_sequence", "compatibility", "roadmap", "highest_priority_next_task", "unresolved")
    if not _required(data, top, "", errors): return errors
    if data["schema_version"] != 1: errors.append("/schema_version: unsupported")
    if data["boot_readiness_claimed"] is not False: errors.append("/boot_readiness_claimed: must remain false")
    integration = data["integration"]
    if _required(integration, (*EXPECTED_COMMITS, "base_branch", "phase_2a_is_ancestor_of_phase_2b"), "/integration", errors):
        for key, expected in EXPECTED_COMMITS.items():
            if integration[key] != expected: errors.append(f"/integration/{key}: milestone SHA mismatch")
        if integration["phase_2a_is_ancestor_of_phase_2b"] is not True: errors.append("/integration: Phase 2A must be integrated into Phase 2B")
    baseline = data["source_baseline"]
    if _required(baseline, ("xnu_commit", "ios_sweet_commit", "sweet_patch_count", "inspection_scope"), "/source_baseline", errors):
        if baseline["xnu_commit"] != "1b191cb58250d0705d8a51287127505aa4bc0789": errors.append("/source_baseline/xnu_commit: mismatch")
        if baseline["ios_sweet_commit"] != "45263bee51df4a0f55cdf9c649af886399488ddb": errors.append("/source_baseline/ios_sweet_commit: mismatch")
        if baseline["sweet_patch_count"] != 81: errors.append("/source_baseline/sweet_patch_count: mismatch")

    inspected = data["inspected_source_paths"]
    _nonempty_list(inspected, "/inspected_source_paths", errors)
    if isinstance(inspected, list) and (len(inspected) != len(set(inspected)) or any(not isinstance(x, str) or not x for x in inspected)):
        errors.append("/inspected_source_paths: paths must be unique non-empty strings")
    map_ids = []
    if not isinstance(data["source_map"], list) or not data["source_map"]: errors.append("/source_map: expected non-empty list")
    else:
        for index, item in enumerate(data["source_map"]):
            path = f"/source_map/{index}"
            if not _required(item, MAP_FIELDS, path, errors): continue
            map_ids.append(item["id"])
            if item["inspection"] not in INSPECTIONS: errors.append(path+"/inspection: unsupported classification")
            if item["inspection"] == "unresolved-mapping":
                if item["source_path"] is not None or item["symbols"] != []: errors.append(path+": unresolved mapping must not invent a path or symbols")
            elif item["source_path"] not in inspected: errors.append(path+"/source_path: path was not directly inspected")
            for field in ("evidence", "dependencies", "missing"):
                _nonempty_list(item[field], path+"/"+field, errors)
            if not isinstance(item["symbols"], list): errors.append(path+"/symbols: expected list")
            for field in ("sweet_behavior", "walleye_requirement", "validation"):
                if not isinstance(item[field], str) or not item[field].strip(): errors.append(path+"/"+field+": must be non-empty")
    if len(map_ids) != len(set(map_ids)): errors.append("/source_map: duplicate IDs")

    claims = data["hardware_claims"]
    if not isinstance(claims, list) or not claims: errors.append("/hardware_claims: expected non-empty list")
    else:
        claim_ids = []
        for index, claim in enumerate(claims):
            path = f"/hardware_claims/{index}"
            if not _required(claim, ("id", "value", "descriptor_path", "provenance", "status"), path, errors): continue
            claim_ids.append(claim["id"])
            if not isinstance(claim["provenance"], str) or not claim["provenance"].startswith("config/msm8998-platform.json#/provenance/"):
                errors.append(path+"/provenance: must reference Phase 2B provenance")
            if claim["status"] not in ("historical-report", "derived-from-historical-report", "derived"):
                errors.append(path+"/status: unsupported evidence status")
            if platform is not None:
                try:
                    if _pointer(platform, claim["descriptor_path"]) != claim["value"]: errors.append(path+"/value: differs from Phase 2B descriptor")
                    provenance_pointer = claim["provenance"].split("#", 1)[1]
                    record = _pointer(platform, provenance_pointer)
                    if not isinstance(record, dict) or not record.get("source"): errors.append(path+"/provenance: referenced record is incomplete")
                except (KeyError, IndexError, TypeError): errors.append(path+": descriptor/provenance pointer does not resolve")
        if len(claim_ids) != len(set(claim_ids)): errors.append("/hardware_claims: duplicate IDs")

    stages = data["initialization_sequence"]
    if not isinstance(stages, list) or len(stages) != len(STAGE_IDS): errors.append("/initialization_sequence: expected all nine ordered stages")
    else:
        if [stage.get("id") for stage in stages if isinstance(stage, dict)] != STAGE_IDS: errors.append("/initialization_sequence: stage IDs/order mismatch")
        for index, stage in enumerate(stages):
            path = f"/initialization_sequence/{index}"
            if not _required(stage, STAGE_FIELDS, path, errors): continue
            if stage["order"] != index + 1: errors.append(path+"/order: must be contiguous and one-based")
            for field in ("preconditions", "inputs", "outputs", "failure_conditions", "offline_invariants", "hardware_dependencies"):
                _nonempty_list(stage[field], path+"/"+field, errors)
            _nonempty_list(stage["firmware_services"], path+"/firmware_services", errors, allow_empty=True)

    compatibility = data["compatibility"]
    if not isinstance(compatibility, list) or not compatibility: errors.append("/compatibility: expected non-empty list")
    else:
        for index, item in enumerate(compatibility):
            path = f"/compatibility/{index}"
            if not _required(item, ("component", "category", "reason"), path, errors): continue
            if item["category"] not in CATEGORIES: errors.append(path+"/category: unsupported")
            if not item["reason"]: errors.append(path+"/reason: empty")

    roadmap = data["roadmap"]
    if not isinstance(roadmap, list) or not roadmap: errors.append("/roadmap: expected non-empty list")
    else:
        ids = []
        for index, item in enumerate(roadmap):
            path = f"/roadmap/{index}"
            if not _required(item, MILESTONE_FIELDS, path, errors): continue
            ids.append(item["id"])
            for field in ("components", "offline_tests", "acceptance", "blockers"):
                _nonempty_list(item[field], path+"/"+field, errors)
            _nonempty_list(item["dependencies"], path+"/dependencies", errors, allow_empty=True)
            if item["complexity"] not in ("low", "medium", "high", "very-high"): errors.append(path+"/complexity: unsupported")
        if len(ids) != len(set(ids)): errors.append("/roadmap: duplicate milestone IDs")
    if not isinstance(data["highest_priority_next_task"], str) or not data["highest_priority_next_task"].startswith("M1:"):
        errors.append("/highest_priority_next_task: must identify M1")
    _nonempty_list(data["unresolved"], "/unresolved", errors)
    forbidden_fragments = ("boot ready", "bootable", "safe loader address")
    rendered = json.dumps(data).lower()
    if any(fragment in rendered for fragment in forbidden_fragments): errors.append("/: contains forbidden readiness/address claim")
    return errors


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("plan", type=Path); args = parser.parse_args()
    try: data = json.loads(args.plan.read_text())
    except (OSError, json.JSONDecodeError) as error: print(json.dumps({"valid":False,"errors":[str(error)]}, indent=2)); raise SystemExit(1)
    platform_path = args.plan.with_name("msm8998-platform.json")
    try: platform = json.loads(platform_path.read_text())
    except (OSError, json.JSONDecodeError) as error: print(json.dumps({"valid":False,"errors":[f"Phase 2B descriptor: {error}"]}, indent=2)); raise SystemExit(1)
    errors = validate(data, platform); print(json.dumps({"valid":not errors,"errors":errors}, indent=2)); raise SystemExit(bool(errors))


if __name__ == "__main__": main()
