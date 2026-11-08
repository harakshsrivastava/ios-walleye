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

- Objective: define a host-validated walleye Apple-style tree and boot-argument schema; do not implement a loader.
- Components: proposed `config/walleye-adt-schema.json`, proposed `tools/validate_walleye_handoff.py`, existing `pexpert/pexpert/arm64/boot.h` ABI mapping.
- Dependencies: complete reservation evidence and producer contract.
- Offline tests: golden/adversarial trees, pointer/range/overflow/ownership checks.
- Acceptance: summary-only reservations cannot produce a handoff; all ranges bounded; no load address selected.
- Blockers: 15 static ranges and five dynamic placements.
- Complexity: medium.

## M3 — Walleye Platform Expert

- Objective: implement compile-only platform identity and safe nub publication.
- Components: proposed `iokit/Kernel/arm/WalleyePlatformExpert.cpp`, `iokit/KernelConfigTables.cpp`, `iokit/conf/files.arm64`.
- Dependencies: M1, M2, verified ADT identities.
- Offline tests: registry model, match-table scan, node allowlist/exclusion fixtures.
- Acceptance: no SWEET match reuse; unknown MMIO nodes remain unpublished; walleye identity exact.
- Blocker: final ADT compatible/name contract.
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
- M2 may implement only schema/validation while reservation evidence is missing; it must reject production of a handoff contract.
- M3 can compile against fixtures but must not claim runtime node safety before M2 resolves.
- M4–M5 remain non-activating until their named evidence gates close.
- M7 must not be started by copying SWEET's `smc #0` path.

The next milestone is M2's schema/validator portion. Its handoff-production path remains blocked until complete reservation and producer evidence exists.

Machine-readable milestone fields, dependencies and acceptance criteria are in `config/xnu-msm8998-port-plan.json` and are enforced by `tools/validate_xnu_msm8998_plan.py`.
