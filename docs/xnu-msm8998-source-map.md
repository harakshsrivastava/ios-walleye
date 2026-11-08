# XNU MSM8998 source map

## Evidence method

The baseline was inspected at Apple XNU commit `1b191cb58250d0705d8a51287127505aa4bc0789`. A disposable worktree was patched with ios-sweet patches `0001` through `0018`, plus `0065` and `0078`, to inspect the final platform-entry, GIC, Platform Expert and SMP paths relevant to this design. The patch source is ios-sweet commit `45263bee51df4a0f55cdf9c649af886399488ddb`. Other claims below are labeled as Phase 2A/2B evidence or unresolved. The worktree is not a project deliverable.

Evidence labels:

- **Direct/base**: inspected in pinned Apple XNU.
- **Direct/patched**: inspected after applying the identified SWEET patches to that baseline.
- **Report**: carried from the verified project reports, not re-derived here.
- **Unresolved**: no inspected mapping or sufficient evidence.

## ARM64 entry and boot arguments

### `osfmk/arm64/start.s` — `_start`, `start_first_cpu`, `common_start` (Direct/patched)

- SWEET behavior: `_start` branches to `start_first_cpu`; x0 is the `boot_args` pointer. The assembly writes EL1 registers, disables interrupts, builds exception/interrupt stacks from linked symbols adjusted by `virtBase - physBase`, creates bootstrap V=P and KVA page tables from `memSize`, establishes TCR/TTBR/MAIR/VBAR, and enables SCTLR/MMU/caches. SWEET patches add direct writes and mappings for framebuffer `0x9c000000`.
- Required walleye behavior: retain the generic path only after its incoming state is documented. Delete/compile out every SWEET framebuffer operation. A validation gate must reject unknown EL, cache/MMU state, boot-argument pointer, image mapping, or writable bootstrap-table assumptions.
- Dependencies: firmware handoff contract, safe image placement, valid boot-argument ABI.
- Missing: initial EL, incoming SCTLR/cache/MMU state, register guarantees, safe physical placement.
- Offline validation: assembly scan forbidding SWEET addresses; boot-argument offset consistency; entry-state fixtures that reject unknown state.

Primary entry uses EL1 registers immediately and contains no primary-CPU EL2-to-EL1 transition. Therefore EL1-compatible entry is a precondition, not an established walleye fact.

### `pexpert/pexpert/arm64/boot.h` — `boot_args` (Direct/base)

- Existing behavior: defines revision/version, `virtBase`, `physBase`, `memSize`, `topOfKernelData`, video state, `deviceTreeP`, `deviceTreeLength`, command line, flags, and `memSizeActual`.
- Required walleye behavior: a separately validated producer contract. Every pointer and range must be aligned, bounded, non-overflowing, and consistent with all reservations. This phase does not implement the producer.
- Dependencies: complete memory ownership and Apple-style tree format.
- Missing: who produces the structure, where it resides, and what physical ranges are safe.
- Offline validation: serialized fixture/layout checks and adversarial range validation.

### `osfmk/arm/arm_init.c` — `arm_init`, `arm_slide_rebase_and_sign_image`, `ml_parse_cpu_topology`, `arm_vm_init`, `serial_init`, `machine_startup` (Direct/patched)

- Existing order: copy boot arguments; early `PE_init_platform(FALSE, args)`; CPU topology; bootstrap CPU/thread/timer; VM construction; diagnostics; `PE_init_platform(TRUE, ...)`; CPU timebase/GIC initialization; `machine_startup`.
- Required walleye behavior: preserve XNU ordering while adding fail-closed data validation before each consumer. Do not treat late validation as protection for earlier assembly or VM accesses.
- Dependencies: validated boot arguments and ADT.
- Missing: which minimal validation code can safely execute before final VM setup.
- Offline validation: source-order assertions and host models for each stage precondition.

The function calls `arm_slide_rebase_and_sign_image` after entering C. Phase 2A found a PIE `MH_EXECUTE`, `_start` entry, 77,056 local relocations, and no dyld/chained-fixup payload. That describes the SWEET artifact; it does not define a walleye loader contract.

## Platform Expert and device tree

### `pexpert/arm/pe_init.c` — `PE_init_platform`, `PE_slide_devicetree` (Direct/base)

- Existing behavior: takes the device-tree pointer/length from `boot_args`, calls `SecureDTInit`, and performs early machine identification. Its late call initializes interrupts and debugging.
- Required walleye behavior: accept only a validated Apple-style tree with explicit identity, `/chosen`, CPU, GIC, memory-ownership and diagnostic schemas.
- Dependencies: FDT-to-ADT translation contract.
- Missing: exact transformation and whether the recovered runtime FDT equals boot-time state.
- Offline validation: golden and malformed tree fixtures; property sizes and ranges checked before MMIO mapping.

### `iokit/KernelConfigTables.cpp` — `gIOKernelConfigTables` (Direct/patched)

- SWEET behavior: matches `SweetPlatformExpert` to `xiaomi,sweet` and `SweetCPU` to `qcom,kryo470`.
- Required walleye behavior: distinct WALLEYE classes and exact schema-owned identities. Never broaden the SWEET matches.
- Dependencies: verified walleye ADT identity strings.
- Missing: final compatible/name contract.
- Offline validation: match-table parser rejects SWEET strings in WALLEYE entries.

### `iokit/Kernel/arm/SweetPlatformExpert.cpp` — `start`, `processTopLevel`, `getTargetName`, `getProductName` (Direct/patched)

- SWEET behavior: subclasses `IODTPlatformExpert`, avoids stock Apple NVRAM assumptions, publishes CPU and top-level nubs, and returns Redmi/SWEET identity.
- Required walleye behavior: replace with `WalleyePlatformExpert`; reuse only the basic nub mechanism. Publish an allowlisted set of validated nodes and use walleye identity.
- Dependencies: safe-node policy and ADT schema.
- Missing: which MMIO-bearing runtime nodes are safe to publish.
- Offline validation: host registry model, allowlist/exclusion tests, and exact identity tests.

### `iokit/Kernel/IOPlatformExpert.cpp` — `IODTPlatformExpert::probe`, `configure`, `createNubs`, `processTopLevel` (Direct/base)

- Existing behavior: matches provider names, creates `IOPlatformDevice` nubs, attaches logical CPU/cluster IDs, publishes NVRAM/CPU/top-level nodes.
- Required walleye behavior: reuse framework behavior through a constrained subclass; avoid the base NVRAM assertion as SWEET does, but do not publish unvalidated nodes.
- Dependencies: topology parser and validated registry properties.
- Missing: walleye NVRAM/power-domain policy.
- Offline validation: registry fixture proves ignored CPUs and unknown devices are not made active providers.

Build registration touches `iokit/conf/files.arm64`; machine selection touches `makedefs/MakeInc.def`, `pexpert/pexpert/arm64/board_config.h`, `config/MASTER.arm64.*`, and a board header such as `pexpert/pexpert/arm64/SWEET.h` (all Direct/patched). WALLEYE must be a new configuration, not an alias for SWEET.

## CPU topology and SMP

### `osfmk/arm64/machine_routines.c` — `ml_parse_cpu_topology` (Direct/patched)

- Existing behavior: iterates `/cpus`, reads each `reg` as physical ID/MPIDR representation, assigns logical CPU and cluster IDs, honors `cpus`/`cpumask`. SWEET defaults to one CPU unless opted in and clamps to eight.
- Required walleye behavior: keep boot-CPU-only default. Reuse the generic parser only after MPIDRs, boot identity, cluster/cache properties and property encoding are known.
- Dependencies: resolved topology evidence.
- Missing: exact MPIDRs, clusters, boot CPU, cache topology, performance classes.
- Offline validation: reject duplicates, gaps, absent/multiple boot CPU, cluster mismatches and count mismatch.

### `iokit/Kernel/arm/SweetCPU.cpp` — `SweetCPU::start`, `startAll`, `initCPU`, `signalCPU`, `startCPU`, `sweet_psci_cpu_on` (Direct/patched)

- SWEET behavior: validates a Kryo 470-specific MPIDR pattern; expects boot CPU/MPIDR zero; treats six A55 plus two A76 cores as one homogeneous SMP group; sends SGI1; invokes PSCI SMC64 `CPU_ON` function `0xC4000003`; panics on suspend/power-down paths.
- Required walleye behavior: complete replacement with `WalleyeCPU`. Firmware invocation must be abstracted and disabled while PSCI/conduit are unknown. No SWEET MPIDR pattern, CPU name, homogeneity or boot CPU assumption can survive.
- Dependencies: PSCI or replacement firmware interface, secondary reset state, cache coherency, GIC per-CPU setup.
- Missing: every firmware/coherency item above.
- Offline validation: mocked firmware state machine and return codes; compile-time proof that boot-CPU-only mode contains no SMC path.

### `osfmk/arm64/start.s` — `sweet_secondary_entry`, `LowResetVectorBase`, `reset_vector`, `start_cpu` (Direct/patched)

- SWEET behavior: `sweet_secondary_entry` assumes PSCI x0 context with MMU/caches off, performs an EL2 setup sequence, and transfers to `LowResetVectorBase`.
- Required walleye behavior: do not reuse. A separate path can be written only from a verified secondary-entry EL/register/cache contract.
- Dependencies/missing: PSCI conduit/version, initial EL, HCR/SCTLR state, coherency and physical-entry rules.
- Offline validation: static register-state contract; SMP feature remains build-disabled while any input is unknown.

`osfmk/arm64/cpu.c` contains `cpu_timebase_init` and generic CPU state machinery (Direct/base). Its bookkeeping is reusable after validated GIC/timer/topology setup; it does not resolve firmware power-on.

## GICv3 and architectural timer

### `pexpert/arm/pe_fiq.c` — `pe_init_fiq`, `find_gicr_pe_base` (Direct/patched)

- SWEET behavior: reads `/arm-io/gic` `reg` tuples, maps GICD/GICR, scans redistributors using MPIDR affinity and fixed stride, wakes the local redistributor, programs timer/SGI priorities and enables the non-secure Group 1 system-register interface. Patch 0017 validates an optional `virtual-timer-intid` PPI.
- Required walleye behavior: reuse mapping/affinity concepts with configuration changes, but isolate all register writes behind a resolved security/ownership policy. Phase 2B provides bases and stride, not region sizes or permission to program them.
- Dependencies: GICD/GICR sizes, MPIDRs, security ownership, ICC_SRE availability.
- Missing: those dependencies and firmware-initialized state.
- Offline validation: mock-MMIO bounds, bounded redistributor scan, affinity match, wake timeout, and zero writes under unknown policy.

### `osfmk/arm64/sleh.c` — `sleh_irq`, `sleh_fiq` (Direct/patched)

- SWEET behavior: reads `ICC_IAR1_EL1`, routes the selected timer PPI to `rtclock_intr`, SGIs to `cpu_signal_handler`, other IDs to the registered handler, handles 1020–1023 as spurious, and EOIs through Group 1.
- Required walleye behavior: retain dispatch categories, but parameterize/select IRQ/FIQ and group behavior only after evidence.
- Dependencies/missing: interrupt group/security routing and SGI allocation.
- Offline validation: pure dispatch model checks spurious, timer, SGI, device and EOI ordering.

### `pexpert/arm/pe_identify_machine.c` — `PE_init_cpu`, `pe_arm_init_interrupts`, `pe_arm_map_interrupt_controller`, `pe_arm_init_timer` (Direct/base)

- Existing behavior: late Platform Expert maps interrupt/timer nodes; `PE_init_cpu` calls `pe_init_fiq`; generic timebase operations are installed.
- Required walleye behavior: preserve order, replace assumed Apple node shapes with the validated schema, and validate sizes before `ml_io_map`.
- Dependencies: ADT schema and GIC policy.
- Missing: complete safe region sizes and policy.
- Offline validation: golden-tree and source-order tests.

### `osfmk/arm64/cpu.c` — `cpu_timebase_init`; `osfmk/arm64/machine_routines.c` — virtual-timer accessors (Direct/base)

- Existing behavior: architecture-generic CNTV/timebase bookkeeping and per-CPU initialization.
- Required walleye behavior: reuse after INTID 19, CNTFRQ, access permissions and routing are established.
- Evidence: INTID 19 is a Phase 2B historical report; counter frequency/routing remain unknown.
- Offline validation: arithmetic/deadline tests and compile-only register-wrapper tests.

## Physical memory, VM, and relocation

### `osfmk/arm64/arm_vm_init.c` — `arm_vm_init`, `arm_vm_physmap_init` (Direct/patched)

- Existing behavior: derives `gPhysBase`, managed size, `avail_start`, physmap, page-table storage and kernelcache physical bounds from `boot_args`. `topOfKernelData` becomes the initial available physical boundary. SWEET adds physmap padding and a persistent hardcoded framebuffer mapping.
- Required walleye behavior: remove the framebuffer mapping and accept only a complete ownership contract that excludes kernel, boot args, ADT and every static/dynamic reservation. The runtime FDT RAM declaration is not such a contract.
- Dependencies: full reservation inventory and kernel/metadata placement.
- Missing: 15 static ranges, five dynamic placements, safe loader map, `topOfKernelData` producer rules.
- Offline validation: a range-set model proves no reserved page is managed and rejects gaps/overflow/overlap.

### `osfmk/arm/pmap/pmap.c` — `pmap_bootstrap` (Direct/base)

- Existing behavior: builds the XNU physical map from the boundary calculated by `arm_vm_init`.
- Required walleye behavior: direct reuse after the upstream memory contract is correct; MSM8998 addresses do not belong here.
- Missing: complete memory contract.
- Offline validation: range model plus call-boundary/source-order assertion.

### Reserved-memory import (Unresolved)

A direct search of the inspected tree found no SWEET/XNU path that imports Linux `/reserved-memory` children into `arm_vm_init` managed ranges. The future integration point must be defined by the handoff/ADT contract before VM initialization. Current summary-only evidence must fail to produce a boot memory contract.

## Diagnostics

### `pexpert/arm/pe_serial.c` — `serial_init`, `register_serial_functions` (Direct/patched)

- SWEET behavior: probes `sweet-fbcon` and registers platform serial functions; earlier SWEET stages directly touch framebuffer `0x9c000000`.
- Required walleye behavior: remove all SWEET framebuffer behavior. With UART type/base/clock unknown, register no MMIO provider and return failure without side effects.
- Dependencies/missing: verified UART hardware and firmware readiness.
- Offline validation: unknown-provider test proves zero MMIO and clean failure.

### `pexpert/arm/pe_kprintf.c` — `PE_init_kprintf` (Direct/base)

- Existing behavior: chooses serial when `serial_init` succeeds, otherwise `console_write_unbuffered`.
- Required walleye behavior: use the structure only if the fallback is proven safe; otherwise introduce a bounded memory ring after safe memory exists. No storage dependency.
- Missing: a safe pre-VM sink and UART evidence.
- Offline validation: buffer bounds/wrap behavior and no-provider failure.

## Unresolved mappings

- Firmware handoff producer and boot shim: intentionally not implemented or mapped.
- Complete reserved-memory translation: no inspected implementation.
- Walleye power management, CPU_OFF/suspend, and coherency controls: no evidence.
- Safe loader addresses: deliberately absent.
- UFS initialization is outside the minimum entry/platform/interrupt architecture and remains blocked by clocks, resets, PHY and firmware link state from Phase 2B.

The machine-readable equivalent, including per-entry dependencies and validation, is `config/xnu-msm8998-port-plan.json`.
