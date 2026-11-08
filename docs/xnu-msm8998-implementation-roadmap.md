# XNU MSM8998 implementation roadmap

The milestones are ordered by the smallest useful offline-verifiable change. Each milestone must remain independently reviewable and must not enable hardware behavior whose contract is unresolved.

## M1 — WALLEYE machine-configuration skeleton

- Status: completed as a compile-only milestone on `feature/walleye-build-skeleton`.
- Objective: create a distinct compile-only target with all hardware services disabled.
- Components: isolated patch for `makedefs/MakeInc.def` and `pexpert/pexpert/arm64/board_config.h`; new `WALLEYE.h` and `MASTER.arm64.walleye` overlays; manifest, validator and compile probe.
- ISA outcome: plain `arm64`, `arm64-apple-darwin22`, `-march=armv8-a -mno-outline-atomics`, and no CPU-specific flag.
- Offline results: manifest validation passed; patch application to the pinned pre-M1 source passed; freestanding host probe compilation passed; all hardware feature gates remained false.
- Tooling boundary: ARM64 Mach-O compilation was unavailable because the executor had no Clang cross-compiler. Linking and a kernel build were not attempted.
- Acceptance: satisfied for the compile-only boundary; no SWEET alias/address, firmware call, framebuffer, UART, SMP, GIC, timer or storage implementation is enabled.
- Remaining blockers: Apple build tooling and every Phase 2C firmware/hardware contract remain unresolved.
- Complexity: low.

Evidence and reproduction details are in `docs/walleye-isa-baseline.md`, `docs/walleye-build-skeleton.md`, and `evidence/walleye-m1-build.json`.

## M2 — Boot-argument and ADT contract

- Status: completed as a strict offline contract and validator on `feature/walleye-boot-contract`; handoff production remains blocked.
- Objective: define a host-validated walleye Apple-style tree and boot-argument schema; do not implement a loader.
- Components: `config/walleye-boot-contract.json`, `tools/validate_walleye_boot_contract.py`, direct mapping to `pexpert/pexpert/arm64/boot.h`, and documented FDT/ADT boundary.
- Dependencies: complete reservation evidence and producer contract.
- Offline tests: schema/version/identity, pointer/range/overflow/overlap/containment, provenance, firmware-state, initialization-order and SWEET-leak checks.
- Acceptance: satisfied for offline validation—summary-only reservations cannot produce a handoff, known ranges are bounded, and no load address is selected.
- Blockers: 15 static ranges and five dynamic placements.
- Complexity: medium.

## M3 — Walleye Platform Expert

- M3A status: completed as a fail-closed, compile-only class and catalogue skeleton on `feature/walleye-platform-expert`.
- M3A components: `patches/xnu/0002-walleye-platform-expert.patch`, `iokit/Kernel/arm/WalleyePlatformExpert.cpp`, `iokit/KernelConfigTables.cpp`, and `iokit/conf/files.arm64`.
- M3A outcome: class and verified board names are distinct from SWEET; the match token is an explicit disabled sentinel; `start()` returns false; no ADT nodes or hardware services are published.
- M3A compile result: the post-patch policy probe produced reproducible ARM64 Mach-O objects; the actual IOKit translation unit is blocked by unavailable generated XNU MIG headers.
- M3B status: completed as a host-side, default-deny identity and safe-node policy on `feature/walleye-adt-validation`; final ADT identity remains unresolved.
- M3B components: `config/walleye-adt-policy.json`, `tools/validate_walleye_adt.py`, and bounded positive/adversarial fixtures under `fixtures/adt/`.
- M3B outcome: only structural `/` and optional `/chosen` fixtures are accepted; identity-bearing properties, hardware nodes, runtime matching, startup, and publication remain rejected.
- M3C status: completed as a standalone pure C11 policy helper on `feature/walleye-native-adt-policy`.
- M3C components: `include/walleye_adt_policy.h`, `src/walleye_adt_policy.c`, reproducible ARM64 Mach-O builds, host/sanitizer harness, and differential Python/native tests.
- M3C outcome: bounded caller-owned spans and stable results enforce the M3B structural policy; no parser, XNU link, runtime call site, or hardware path exists.
- M3D objective: stage the unchanged helper into an isolated WALLEYE XNU patch and build source list without calling it from Platform Expert.
- Dependencies: M1, M2, a validated ADT producer/identity, and base-start property requirements.
- Offline tests: registry model, exact match-table scan, node allowlist/exclusion fixtures, and unknown-MMIO rejection.
- Acceptance: no SWEET match reuse; unknown MMIO nodes remain unpublished; final identity has evidence; runtime startup remains disabled until every gate is satisfied.
- Blocker: final ADT compatible/name contract and safe-node schema.
- Complexity: medium.

## M4 — Policy-driven GICv3 and timer layer

- Objective: move SWEET assumptions behind explicit platform data and a no-write unknown policy.
- Components: `pexpert/arm/pe_fiq.c`, `osfmk/arm64/sleh.c`, `pexpert/pexpert/arm/protos.h`.
- Dependencies: M2; GIC sizes/security/ICC state; counter frequency/routing.
- Offline tests: mock MMIO, redistributor affinity/bounds/timeout, pure IRQ dispatch model.
- Acceptance: known bases and stride parse; unknown security performs zero writes; INTID 19 validates as a PPI.
- Blocker: GIC security ownership and ICC system-register availability.
- Complexity: high.

## M5 — Boot-CPU-only topology and memory boundary

- Objective: allow only a verified primary CPU and a complete managed-memory set.
- Components: `osfmk/arm64/machine_routines.c`, `osfmk/arm64/arm_vm_init.c`, `osfmk/arm/pmap/pmap.c`.
- Dependencies: M2; boot MPIDR; complete boot-time memory ownership.
- Offline tests: topology fixtures, range-set model, source-order assertions.
- Acceptance: exactly one verified boot CPU; no secondary firmware call; no reserved page managed.
- Blockers: boot MPIDR, reservation placements, `topOfKernelData` contract.
- Complexity: high.

## M6 — Fail-safe diagnostics

- Objective: provide bounded storage-free diagnostics with no unknown MMIO access.
- Components: `pexpert/arm/pe_serial.c`, `pexpert/arm/pe_kprintf.c`, `osfmk/console/serial_console.c`.
- Dependencies: M5 supplies safe buffer memory.
- Offline tests: buffer bounds/wrap, concurrency policy, zero-MMIO unknown-provider path.
- Acceptance: no SWEET framebuffer address; failure is side-effect free; bounded memory use.
- Blocker: UART evidence for hardware output.
- Complexity: medium.

## M7 — Secondary CPU firmware adapter

- Objective: add `WalleyeCPU` only after every firmware/coherency contract is evidenced.
- Components: proposed `iokit/Kernel/arm/WalleyeCPU.cpp`, `osfmk/arm64/start.s`, `osfmk/arm64/cpu.c`.
- Dependencies: M4, M5, PSCI/conduit and secondary-entry contracts.
- Offline tests: mocked firmware state machine, error/timeout paths, static EL/register contract.
- Acceptance: no hardcoded MPIDR pattern; GIC/timer per-CPU initialization gated; firmware failures fail closed.
- Blockers: PSCI, reset EL/state, cache/coherency, power management.
- Complexity: very high.

## Stop/go rules

- M1 is complete at the compile-only boundary; it does not authorize hardware initialization.
- M2's schema/validator portion is complete; production of a handoff remains rejected while reservation and producer evidence is missing.
- M3A remains compile-only and fail-closed. M3B validates synthetic registry fixtures only. M3C is compiled but uncalled. M3D may stage source only; runtime invocation remains blocked until native ADT identity and producer gates resolve.
- M4–M5 remain non-activating until their named evidence gates close.
- M7 must not be started by copying SWEET's `smc #0` path.

The next source-level milestone is M3D: stage the unchanged helper in the pinned XNU source/build list without a runtime call site. Final matching, base-class startup, native parsing, and node publication remain blocked.

Machine-readable milestone fields, dependencies and acceptance criteria are in `config/xnu-msm8998-port-plan.json` and are enforced by `tools/validate_xnu_msm8998_plan.py`.
