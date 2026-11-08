# Native WALLEYE ADT policy helper

## Scope

M3C implements the M3B structural policy as a pure C11 helper. It validates a caller-owned normalized representation; it does not parse Apple Device Tree bytes, Linux FDT, JSON, IOKit objects, or boot arguments. The helper is not linked into XNU and has no runtime call site.

`WALLEYE_ADT_VALID_STRUCTURAL` means only that the normalized input satisfies policy version 1. It does not resolve the four M3B policy gaps, any of the 38 M2 requirements, or boot readiness.

## Public representation

`include/walleye_adt_policy.h` exposes:

- `walleye_adt_span`: pointer, explicit length, and explicit capacity;
- `walleye_adt_node`: bounded path span, parent index, depth, and node type;
- `walleye_adt_property`: name/value spans, owning node index, and property type;
- `walleye_validate_normalized_adt()`: policy version, node array/count, property array/count, and declared normalized size.

The helper never relies on NUL termination. A nonzero-capacity span requires a non-null pointer, and `length` must not exceed `capacity`. The representation uses compiler-provided fixed-width integer types and caller-owned storage.

There is no allocation, recursion, exception handling, RTTI, global mutable state, libc call, IOKit dependency, or hardware access. File-local constants are immutable.

## Bounds and logical size

Policy version 1 enforces:

- at most two nodes;
- depth at most one;
- at most four properties per node;
- property values at most 64 bytes;
- normalized logical size at most 4096 bytes;
- exactly one root `/` at index zero;
- optional `/chosen` with the root as parent;
- exactly one `name` string property per node.

Logical size is architecture-independent policy accounting:

```text
16 * node_count
+ 24 * property_count
+ all path, property-name, and property-value lengths
```

The caller-supplied size must equal this checked calculation. All additions and multiplications are overflow-checked.

## Policy behavior

The root must have the exact bytes `name = device-tree`; optional `/chosen` must have `name = chosen`. Every other path, property, type, or value is denied. Identity-bearing properties such as `compatible` are therefore rejected, including SWEET/Xiaomi values. Hardware node types and paths are rejected.

Stable result values distinguish structural success, invalid arguments, unsupported policy versions, malformed structure, bounds errors, duplicates, unsupported nodes/properties, and invalid values.

## Compilation

Debian Clang 19.1.7 compiled `src/walleye_adt_policy.c` twice with:

```text
--target=arm64-apple-darwin22
-march=armv8-a -mno-outline-atomics
-std=c11 -ffreestanding -fno-builtin -fno-stack-protector -nostdinc
```

Both outputs were byte-identical ARM64 Mach-O `MH_OBJECT` files:

- size: 4,128 bytes;
- SHA-256: `3a4c5eabcf96aaa53a234bc44e1a41c4b132e61e2e9c1e02810d83652917a3cb`;
- exported validator symbol: `_walleye_validate_normalized_adt`.

No linking or kernel build was attempted.

## Host and differential validation

`tests/native/walleye_adt_policy_test.c` exercises valid structural inputs and all requested malformed, duplicate, bounds, pointer, parent, version, identity, and hardware cases. The host executable passed under normal execution and under AddressSanitizer plus UndefinedBehaviorSanitizer.

`tests/test_walleye_native_adt_policy.py` maps supported M3B JSON tree fixtures into the normalized C representation and compares native decisions with `tools/validate_walleye_adt.py`. Metadata not represented by the C API is rejected by the adapter before calling native code; it is never silently counted as an agreement.

Generated binaries and logs remain under ignored `build/` and are not committed.

## Integration boundary

M3A remains unchanged: its match token is disabled, `WalleyePlatformExpert::start()` returns false, and it publishes no nodes. M3C introduces no native parser and no hardware initialization.

The smallest next step is an isolated XNU patch that stages the unchanged helper and header into the pinned source/build list without adding a runtime call site. Any call from Platform Expert remains blocked until native ADT production, final identity, memory ownership, and other M2 requirements resolve.
