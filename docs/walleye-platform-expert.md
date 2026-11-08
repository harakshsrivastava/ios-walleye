# WALLEYE Platform Expert skeleton

## Scope and safety boundary

M3A adds a real `WalleyePlatformExpert` translation unit to the pinned SWEET-patched XNU layout. It is compile-only: the class is present only in a WALLEYE build, its catalogue personality uses the deliberately non-hardware sentinel `__walleye_m3a_disabled__`, and `start()` returns `false`. It cannot match a real board description or publish device nodes.

This preserves M2's `valid_with_unresolved` result. M3A defines neither an Apple Device Tree compatible string nor an FDT-to-ADT translator, load address, firmware conduit, CPU-start path, interrupt policy, timer policy, or peripheral driver.

## Directly inspected interfaces

| Source | Symbol or interface | Observed behavior | M3A decision |
| --- | --- | --- | --- |
| `iokit/Kernel/arm/SweetPlatformExpert.cpp` | `SweetPlatformExpert`, `start`, `processTopLevel` | The SWEET subclass starts the base expert and publishes `/cpus`, top-level, and `/arm-io` nubs | Reuse only the subclass convention; do not copy publication behavior |
| `iokit/KernelConfigTables.cpp` | `gIOKernelConfigTables` | A built-in SWEET personality matches `xiaomi,sweet`; later entries match SWEET CPU and peripherals | Add a separately guarded WALLEYE personality with a disabled sentinel and no CPU/peripheral entries |
| `iokit/conf/files.arm64` | IOKit C++ source list | Includes `SweetPlatformExpert.cpp` unconditionally; its source guard makes other targets empty translation units | Add the WALLEYE source using the same source-list convention |
| `iokit/Kernel/IOPlatformExpert.cpp` | `IODTPlatformExpert::probe` | Calls `provider->compareNames()` with `IONameMatch` | A match token is structurally required, so M3A uses an explicit non-hardware sentinel rather than inventing final ADT identity |
| `iokit/Kernel/IOPlatformExpert.cpp` | `IODTPlatformExpert::configure`, `processTopLevel`, `createNubs` | Base configuration can publish NVRAM, CPU, and top-level nubs; CPU nubs acquire logical topology identifiers | Override `processTopLevel` with no publication and keep startup disabled |
| `iokit/Kernel/IOPlatformExpert.cpp` | `IOPlatformExpert::start` | Establishes global platform state, power domains, interrupt-controller storage, clock properties, and calls `configure` | Do not call it until M2 prerequisites and an M3B safe-node policy are validated |
| `iokit/Kernel/IOStartIOKit.cpp` | `InitIOKit`, `StartIOKitMatching` | Creates the `IOPlatformExpertDevice` root from the already-ingested device tree, then starts catalogue matching | M3A does not alter this path |
| `pexpert/arm/pe_init.c` | `PE_init_platform` | Copies ADT pointer/length from `boot_args`, calls `SecureDTInit`, and performs machine identification before IOKit matching | Platform Expert code cannot make an Android FDT acceptable; M2 remains authoritative |
| `pexpert/arm/pe_identify_machine.c` | `pe_identify_machine` | Reads CPU and `/arm-io` properties and initializes frequency information | No WALLEYE values are supplied by M3A |

The direct source inspection used XNU `1b191cb58250d0705d8a51287127505aa4bc0789` after all 81 patches from ios-sweet `45263bee51df4a0f55cdf9c649af886399488ddb`. The existing full-stack worktree survived M2, so the expensive 81-patch operation was not repeated.

## Source changes

`patches/xnu/0002-walleye-platform-expert.patch` applies after the 81 SWEET patches and M1 patch `0001`:

- `pexpert/pexpert/arm64/WALLEYE.h` enables compilation of the Platform Expert class while keeping runtime startup and every hardware feature disabled.
- `iokit/Kernel/arm/WalleyePlatformExpert.cpp` defines the distinct subclass and verified board/product names.
- `iokit/KernelConfigTables.cpp` adds a WALLEYE-only, fail-closed personality.
- `iokit/conf/files.arm64` adds the new translation unit.

Unsupported paths are explicit: startup returns `false`, ADT publication is empty, halt/restart returns `-1`, platform functions return `kIOReturnUnsupported`, and sleep panics rather than invoking an unknown firmware contract. There are no MMIO literals, SWEET identifiers, framebuffer/UART operations, SMC calls, CPU-start logic, or GIC/timer writes in the new source.

`getTargetName()` returns `walleye` and `getProductName()` returns `Google Pixel 2`, both from the Phase 2B identity record. These names do not define the unresolved ADT compatible property.

## Compile-only validation

The M3A patch passed `git apply --check` after the preserved 81-patch stack and M1. Debian Clang 19.1.7 was used with:

```text
--target=arm64-apple-darwin22 -march=armv8-a -mno-outline-atomics
```

Compiling the actual `WalleyePlatformExpert.cpp` advanced through the WALLEYE board header and stopped in the common XNU IOKit include chain at missing generated MIG header `mach/clock_reply_server.h`. No WALLEYE diagnostic preceded that dependency failure, and no object was produced. This is not source-compilation success.

The smaller post-patch policy probe compiled twice as byte-identical 400-byte ARM64 Mach-O `MH_OBJECT` files. SHA-256:

```text
67a7cce9bcaf9c4c7f9d7ebd2fbd931464f4cfbe7478cf4bdcfe3910c2d7a69a
```

It contains `_walleye_m3a_platform_expert_probe`, no relocations, and was not linked. Exact commands and hashes are recorded in `evidence/walleye-m3a-validation.json`.

## Remaining blockers and M3B boundary

M3B should define and validate, offline, the final ADT root identity and a minimal safe-node allowlist. It may use registry fixtures to prove that unknown and MMIO-bearing nodes remain unpublished. Runtime `start()` must remain disabled until the ADT producer, boot-argument pointers, complete memory ownership, CPU topology, and required base-Platform-Expert inputs are validated. M3B should not add CPU startup, PSCI, GIC, timer, UART, framebuffer, storage, or physical-device execution.
