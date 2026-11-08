# WALLEYE Linux FDT / Apple device-tree boundary

## The formats are not interchangeable

The recovered WALLEYE artifact is a Linux flattened device tree (FDT) version 17. FDT uses a standard header, big-endian cells, structure tokens, a strings block, phandles/fixups and Linux binding conventions.

The pinned XNU code calls its input a flattened device tree, but its in-memory representation is different. `pexpert/pexpert/device_tree.h` defines a depth-first stream of:

- `DeviceTreeNode { uint32_t nProperties; uint32_t nChildren; }`;
- `DeviceTreeNodeProperty { char name[32]; uint32_t length; value... }`;
- property values padded to a four-byte boundary.

`SecureDTInit(base, size)` in `pexpert/gen/device_tree.c` bounds that Apple-format region and the `SecureDT*` traversal functions interpret those records directly. Passing an FDT blob at `boot_args.deviceTreeP` would therefore make XNU interpret FDT header/token bytes as Apple node counts and properties.

## Actual boot-argument boundary

The ARM64 `boot_args` structure contains `void *deviceTreeP` and `uint32_t deviceTreeLength`. Early `PE_init_platform(FALSE, args)` copies those values into `PE_state`, calls `SecureDTInit`, and immediately performs machine identification. The pointer is not an FDT pointer merely because both ecosystems use the phrase “flattened device tree.”

The contract consequently requires:

```text
handoff format = apple-device-tree-flat
Linux evidence format = linux-fdt-v17
direct reuse permitted = false
```

Both the ADT address and length remain unresolved.

## Required translation work

A future host-side translator would need an allowlisted schema, not a generic byte conversion. At minimum it must produce:

1. root identity properties and the final WALLEYE Platform Expert match;
2. `/chosen` and an Apple `/chosen/memory-map` with correctly sized `DTMemoryMapRange` properties;
3. `/cpus` records with verified MPIDRs, boot state, topology and property widths expected by `ml_parse_cpu_topology`;
4. `/arm-io` plus only validated children and parent-relative range semantics;
5. GIC/timer properties with complete ranges and resolved policy;
6. a memory-ownership description consistent with `physBase`, `memSize`, `topOfKernelData`, the kernel, boot arguments and the ADT itself.

Property names that happen to coincide do not prove compatible encoding or semantics. FDT phandles, `#address-cells`, interrupt tuples, `/reserved-memory`, overlays and Linux-compatible strings require explicit translation decisions.

## Inputs that cannot yet be translated safely

- the 15 static reservation ranges are absent from surviving evidence;
- five dynamic reservations have no placements;
- runtime-FDT state is not proven equal to firmware handoff state;
- boot CPU MPIDR and complete topology are unknown;
- GIC region sizes and security ownership are unknown;
- counter frequency and routing are unknown;
- final WALLEYE ADT compatible/model/target strings are unresolved;
- kernel, boot-argument and tree placement are unknown.

Until those inputs exist, the validator deliberately refuses to produce managed-memory ranges or an ADT handoff pointer. The runtime FDT remains provenance-bearing hardware evidence only.
