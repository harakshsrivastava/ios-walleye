# WALLEYE safe-node policy

## Default-deny model

Policy version 1 accepts only a synthetic root `/` and optional empty structural `/chosen`. Every node path and property must be listed explicitly in `config/walleye-adt-policy.json`; anything else is invalid.

| Path | Type | Required property | Children | IOKit publication |
| --- | --- | --- | --- | --- |
| `/` | `root` | `name`: string, exactly `device-tree` | optional `/chosen` | disabled |
| `/chosen` | `structural` | `name`: string, exactly `chosen` | none | disabled |

Each property carries a policy provenance identifier. Duplicate properties are representable and rejected because fixture properties are arrays rather than JSON object keys.

## Hard bounds

- maximum nodes: 2;
- maximum depth: 1 below the root;
- maximum properties per node: 4;
- maximum property payload: 64 bytes under the documented synthetic sizing rules;
- maximum fixture file: 4096 bytes;
- duplicate JSON keys, node paths, and property names: rejected.

These bounds cannot be expanded without a policy version change.

## Rejected content

The validator rejects unknown paths and explicitly denies `/arm-io`, `/cpus`, `/gpu`, `/display`, `/storage`, `/ufs`, `/radio`, `/modem`, `/security`, and `/chosen/memory-map`, including descendants. No operational GPU, display, storage, radio, security, CPU, interrupt, timer, diagnostic, or peripheral declaration is accepted.

Root identity properties are also rejected while identity is unresolved. This prevents a fixture from smuggling `google,walleye`, `xiaomi,sweet`, or another unevidenced value through `compatible`, `model`, `device_type`, or `target-type`.

## Validation and statuses

`tools/validate_walleye_adt.py` uses only the Python standard library. It validates policy version, project dependencies, identity metadata, provenance, runtime gates, tree structure, paths, types, sizes, duplicates, and allowlist membership.

Statuses are:

- `invalid`: any policy, structure, identity, provenance, type, bound, or project-consistency error;
- `valid_with_unresolved`: offline structure is consistent but ADT/M2 requirements remain unresolved;
- `valid_offline`: reserved for a structurally valid policy with no unresolved items; it still would not imply boot compatibility.

The current reference is `valid_with_unresolved`: four policy-level gaps plus all 38 M2 items remain explicit.

## M3A preservation

Validation checks that M3A still has:

- `runtime_match_enabled = false`;
- the `__walleye_m3a_disabled__` match sentinel;
- `start_supported = false` and source `return false`;
- `adt_node_publication = none`;
- firmware calls disabled.

M3B introduces no XNU patch because host-side policy validation does not justify changing the fail-closed runtime source.

## Future revisions

Any additional node, property, type, or size requires an explicit policy revision, provenance, negative tests, and a renewed assessment of whether it can cause matching, resource resolution, nub registration, or hardware access. The smallest next source-level step is a compile-only pure policy helper over a normalized, already-bounded representation; it must remain uncalled by runtime startup until native ADT identity and producer evidence resolve.
