# WALLEYE ADT identity contract

## Identity layers

M3B keeps physical board identity separate from Apple Device Tree identity.

The physical target is established project evidence:

- manufacturer: Google;
- product: Pixel 2;
- codename: walleye;
- SoC: Qualcomm MSM8998.

Those values do not establish a native ADT root `compatible`, `model`, `device_type`, or `target-type` value. `config/walleye-adt-policy.json` therefore records the final match property, match value, and production ADT producer as `null` / `unresolved`. Android identity strings are not promoted into ADT facts.

## Directly inspected XNU behavior

| Path | Symbol | Confirmed behavior |
| --- | --- | --- |
| `pexpert/pexpert/device_tree.h` | `DeviceTreeNode`, `DeviceTreeNodeProperty` | Native Apple flattened trees are count-based node/property records, not Linux FDT tokens or the M3B JSON model |
| `pexpert/gen/device_tree.c` | `SecureDTInit`, `SecureDTLookupEntry`, `SecureDTGetProperty` | Establishes native-tree bounds and performs native traversal/property lookup |
| `pexpert/arm/pe_init.c` | `PE_init_platform` | Initializes the native tree from `boot_args`, finds the `device-tree` root by `name`, and conditionally reads `model`, `target-type`, and `/chosen` properties before IOKit matching |
| `iokit/Kernel/IODeviceTreeSupport.cpp` | `IODeviceTreeAlloc`, `MakeReferenceTable` | Converts native ADT nodes and every property into IOKit registry entries and `OSData` properties |
| `iokit/Kernel/IODeviceTreeSupport.cpp` | `IODTCompareNubName` | Matches against `name`, `compatible`, `device_type`, or `model` |
| `iokit/Kernel/IOPlatformExpert.cpp` | `IODTPlatformExpert::probe` | Compares the built-in personality's `IONameMatch` value with the root provider |

This behavior identifies possible carrier properties; it does not identify the correct WALLEYE value. SWEET's `xiaomi,sweet` match remains SWEET-specific.

## Version-1 contract

The policy distinguishes:

- verified physical identity with Phase 2B provenance;
- unresolved ADT root matching property and value;
- unresolved production producer and serialization;
- directly inspected XNU property names;
- an offline-only JSON fixture producer marked `test-only`;
- structural root properties accepted by the current safe-node policy.

The only accepted root property is `name = "device-tree"`, because `PE_init_platform` directly searches for it. It is structural, not a board match. Until identity resolves, `compatible`, `model`, `device_type`, and `target-type` are rejected in fixtures rather than guessed.

Policy version 1 has no optional root properties and rejects every unknown property. Its required production format is `apple-device-tree-flat`, but the production producer is unresolved. The validator input is the separate `walleye-synthetic-adt-registry-v1` JSON model, and direct Linux FDT reuse is forbidden.

The validator rejects incorrect board data, missing provenance, conflicting ADT declarations, SWEET/Xiaomi strings, unsupported versions, and identity values presented as verified without policy evidence.

## Synthetic representation boundary

`fixtures/adt/*.json` are bounded registry models designed for policy tests. They intentionally use property arrays so duplicate property names remain detectable. They are not native ADT blobs, an ADT serializer, an FDT converter, or proof that an equivalent native tree would pass XNU's binary parser.

The reference fixture validates as `valid_with_unresolved`. This means only that its offline structure and project dependencies are consistent. It does not enable the M3A match sentinel, call `WalleyePlatformExpert::start()`, publish IOKit nubs, or establish boot compatibility.

## Producer requirements

A future production identity requires independent evidence for:

1. the exact native root property used by the WALLEYE personality;
2. the exact value and encoding of that property;
3. a bounded native ADT serializer or independently obtained producer;
4. consistency with every `boot_args` pointer and memory-ownership constraint;
5. native-fixture equivalence tests against the inspected XNU record layout.

All 38 M2 boot-critical requirements remain unresolved.
