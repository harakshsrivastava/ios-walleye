# WALLEYE versioned boot-information contract

## Scope

`config/walleye-boot-contract.json` describes the information a future handoff producer would have to supply before the pinned XNU entry path could be considered. It is an offline validation input, not a loader, boot shim, Apple device tree, load-address recommendation, or assertion that firmware can enter XNU.

The reference contract validates as `valid_with_unresolved`. That means the surviving hardware evidence is internally consistent while boot-critical inputs remain absent. It is never a boot-readiness state.

## Directly inspected XNU interfaces

| Source | Structure or consumer | Directly observed behavior | Contract consequence |
| --- | --- | --- | --- |
| `pexpert/pexpert/arm64/boot.h` | `boot_args`, `Boot_Video` | Declares `Revision`, `Version`, `virtBase`, `physBase`, `memSize`, `topOfKernelData`, video fields, `machineType`, `deviceTreeP`, `deviceTreeLength`, 608-byte command line, `bootFlags`, and `memSizeActual` | The contract lists each field separately and leaves producer-owned values unresolved |
| `osfmk/arm64/start.s` | `_start`, `start_first_cpu` | `_start` transfers directly to the primary entry path; generated `BA_*` offsets are used before C validation | Incoming pointer, execution state, image mapping and writable bootstrap-table state are preconditions |
| `osfmk/arm64/genassym.c` | `BA_VIRT_BASE`, `BA_PHYS_BASE`, `BA_MEM_SIZE`, `BA_TOP_OF_KERNEL_DATA`, `BA_BOOT_FLAGS` | Assembly offsets are generated from the C structure | A producer must use the exact pinned layout, not a similar Linux structure |
| `osfmk/arm/arm_init.c` | `arm_init` | Copies the supplied structure into `const_boot_args`, calls early `PE_init_platform(FALSE, args)`, parses topology, then constructs VM state | Validation must occur before the corresponding consumer; later checks cannot repair an unsafe assembly handoff |
| `pexpert/arm/pe_init.c` | `PE_init_platform` | Copies `deviceTreeP`, length and video fields into `PE_state`, calls `SecureDTInit`, then identifies the machine; the late call initializes interrupt/debug paths | The tree pointer and size must already identify a bounded Apple-format tree |
| `pexpert/pexpert/device_tree.h` | `DeviceTreeNode`, `DeviceTreeNodeProperty`, `DTMemoryMapRange` | Defines Apple's flattened node/property layout and physical range pairs | Android FDT tokens cannot be passed through as ADT bytes |
| `pexpert/gen/device_tree.c` | `SecureDTInit`, traversal APIs | Establishes a bounded region, rejects pointer arithmetic overflow, and walks node/property records with 4-byte property padding | The contract requires an explicit format and bounded pointer/length pair |
| `osfmk/arm64/arm_vm_init.c` | `arm_vm_init` | Derives physical/virtual bases, managed size, physmap, `avail_start`, and page-table storage from boot arguments; `topOfKernelData` becomes the first available boundary | RAM declaration alone cannot determine loader placement or managed ownership |
| `osfmk/arm64/arm_vm_init.c` | `/chosen/memory-map` consumers | Reads Apple `DTMemoryMapRange` properties such as `TrustCache`, `AuxKC`, and `AuxKC-mach_header` | Linux `/reserved-memory` is not a substitute for the Apple memory-map node |
| `osfmk/arm64/machine_routines.c` | `ml_parse_cpu_topology` | Walks `/cpus`, reads `reg`, state and cache/topology properties, and identifies a boot CPU | CPU count alone cannot produce a safe ADT CPU description |
| `pexpert/arm/pe_identify_machine.c` | `pe_identify_machine` | Reads `/cpus` frequency properties and `/arm-io` platform data | Frequencies, register shapes and identities require target evidence |

The paths and symbols above were inspected in the pinned Apple source plus the applicable SWEET patch stack. Firmware-entry behavior, safe placement and a WALLEYE ADT producer remain unresolved rather than inferred from these consumers.

## Contract model

The version-1 JSON contract contains:

- exact WALLEYE board identity and an unresolved final ADT identity;
- explicit primary execution-state requirements;
- unresolved kernel physical placement and entry metadata;
- the pinned `boot_args` ABI and individually tracked fields;
- the observed runtime-FDT RAM declaration as evidence, not ownership;
- reserved-memory summary counts with no invented placements;
- separate Linux FDT evidence and required Apple flattened-tree handoff;
- firmware, GIC and timer prerequisites with writes/enables disabled;
- ordered initialization dependencies;
- provenance records for every carried hardware value;
- a non-empty boot-critical unresolved inventory.

Addresses and sizes use unsigned 64-bit hexadecimal strings. A placed range carries an explicit power-of-two alignment. The validator checks addition overflow, alignment, overlap, reservation containment and Phase 2B consistency.

## Validation policy

`tools/validate_walleye_boot_contract.py` returns:

- `invalid`: malformed, inconsistent, guessed, unsupported or provenance-free input;
- `valid_with_unresolved`: structurally sound evidence with at least one unresolved dependency;
- `valid_offline`: a structurally complete offline contract with no unresolved inputs. This category still does not assert execution or boot success.

The validator rejects a readiness claim, Linux FDT as the handoff format, unsupported versions, wrong identity, SWEET-only values, guessed loader or firmware values, invalid dependency order, memory overflow/overlap, out-of-RAM reservations and Phase 2B drift.

## Current unresolved requirements

- initial exception level, x0 value, MMU/cache state and writable bootstrap mappings;
- kernel physical location, entry and size;
- every actual boot-argument value and its producer;
- complete boot-time memory ownership and all reservation placements;
- final ADT identity and FDT-to-ADT transformation;
- CPU MPIDRs, boot CPU and topology;
- PSCI/secure-monitor behavior;
- GIC sizes, security ownership and ICC access;
- counter frequency, timer routing and register access.

No safe loader range is derived from the runtime FDT memory declaration.
