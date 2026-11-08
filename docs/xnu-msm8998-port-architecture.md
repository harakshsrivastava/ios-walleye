# Minimal XNU MSM8998 port architecture

## Scope

This architecture defines the smallest reviewable source boundary for adapting the ios-sweet XNU work to walleye. It does not define a loader, modify a boot image, choose a physical load address, or claim that XNU can start on the device. Unknown firmware state is a hard gate, not a value to be filled by analogy with another Qualcomm phone.

Phase 2B already contains Phase 2A in a linear history. The current design therefore builds on the verified SWEET binary/source analysis and the `valid_with_unresolved` MSM8998 descriptor without merging histories.

## Design rules

1. Create a distinct `WALLEYE` machine configuration. Do not rename or alias `SWEET`.
2. Keep entry, GIC, timer, CPU and VM code disabled or fail-closed until its complete precondition contract validates.
3. Treat the runtime FDT as evidence, not proof of bootloader-time ownership or initialization.
4. Keep the boot CPU as the only selectable CPU until topology and firmware interfaces resolve.
5. Permit no diagnostic MMIO when UART/framebuffer state is unknown.
6. Maintain provenance at the host-side boundary and translate only validated fields into an Apple-style device tree.
7. Separate architecture-generic XNU mechanisms from device-policy decisions.

## Minimum source boundary

The future implementation needs six narrow adapters rather than a broad fork:

- a WALLEYE board/machine configuration with conservative ISA and feature flags;
- a validated boot-argument/ADT contract producer interface, but no producer in this project phase;
- `WalleyePlatformExpert` for identity and safe nub publication;
- GICv3/timer platform data and policy separated from generic mapping/dispatch code;
- a boot-CPU-only topology path followed later by a separate `WalleyeCPU` firmware adapter;
- a no-MMIO diagnostic fallback, optionally extended when UART evidence exists.

`arm_vm_init` and pmap remain generic consumers. The fix belongs in the memory contract delivered to them, plus removal of SWEET framebuffer mappings—not in MSM8998-specific page-table rewrites.

## Initialization sequence

### 1. Firmware entry contract validation

- Preconditions: an immutable contract from a future handoff producer.
- Inputs: entry EL, x0 boot-argument pointer, MMU/cache state, image mapping and writable bootstrap table state.
- Output: a validated entry-state record consumed by `_start`/`start_first_cpu` policy.
- Failure: unknown/mismatched EL, unbounded pointer, unsupported mapping or ambiguous cache/MMU state.
- Firmware services: none invoked; this validates state already supplied.
- Offline invariants: no address selection, all state explicit, unknown rejects.
- Hardware dependency: actual firmware handoff evidence.

Architectural requirement: the inspected primary entry writes EL1 registers and assumes an EL1-compatible environment. Verified walleye behavior: none.

### 2. Primary CPU execution-state validation

- Preconditions: stage 1 succeeds.
- Inputs: `CurrentEL`, MPIDR, required ISA features and relevant control-register state.
- Output: a primary CPU capability record.
- Failure: unsupported EL/ISA, unknown coherency, or SWEET-specific CPU values.
- Firmware services: none.
- Offline invariants: allowlisted feature matrix; no Kryo 470 or ARMv8.2 assumption copied into WALLEYE.
- Hardware dependency: Kryo 280 feature evidence.

### 3. Memory and reservation validation

- Preconditions: entry state valid and complete boot-time ownership evidence.
- Inputs: kernel/ADT/boot-argument placement, declared RAM and all 20 reservation children after dynamic placement.
- Output: non-overlapping kernel-managed ranges and a justified `topOfKernelData` boundary.
- Failure: overflow, overlap, unplaced dynamic reservation, unexplained gap or use of runtime RAM as a loader-safe map.
- Firmware services: none.
- Offline invariants: unsigned 64-bit, page-aligned, bounded ranges; every owned page has one owner.
- Hardware dependency: 15 static ranges and five resolved dynamic placements.

The current descriptor cannot pass this stage. That is intentional.

### 4. Early diagnostics

- Preconditions: stage 3 supplies safe memory for a bounded buffer.
- Inputs: either a validated UART descriptor or a bounded memory-ring configuration.
- Output: an explicit diagnostic sink or no-sink state.
- Failure: selecting unknown MMIO, using SWEET framebuffer `0x9c000000`, or unbounded logging.
- Firmware services: none.
- Offline invariants: unknown UART performs zero MMIO; ring has deterministic bounds/wrap behavior.
- Hardware dependency: UART evidence only if hardware output is requested.

### 5. Platform Expert initialization

- Preconditions: boot arguments and ADT validate.
- Inputs: exact walleye identity and an allowlist of safe nodes.
- Output: `WalleyePlatformExpert` and registered CPU/GIC/timer nubs that carry only validated properties.
- Failure: identity mismatch, missing required node, invalid property size, or unknown MMIO node.
- Firmware services: none.
- Offline invariants: `xiaomi,sweet` and `qcom,kryo470` cannot match; unknown nodes remain unpublished.
- Hardware dependency: final FDT-to-ADT identity/property contract.

### 6. GICv3 setup

- Preconditions: platform data, complete GIC MMIO sizes, CPU MPIDR and security policy validate.
- Inputs: GICD/GICR ranges, `0x20000` stride, affinity, group ownership and ICC interface availability.
- Output: local redistributor awake and CPU interface configured.
- Failure: unknown ownership, missing affinity, out-of-range scan, wake timeout or inaccessible system-register interface.
- Firmware services: a documented statement of firmware-owned GIC state; no guessed service calls.
- Offline invariants: bounded redistributor scan; unknown policy permits no writes.
- Hardware dependency: GIC security/ownership and region sizes.

The bases `0x17a00000`/`0x17b00000` and stride are historical evidence with Phase 2B provenance. They do not authorize register writes.

### 7. Architectural timer setup

- Preconditions: local GIC is configured and counter state is known.
- Inputs: virtual timer INTID 19, counter frequency, group/route and register access.
- Output: per-CPU CNTV/XNU timebase state.
- Failure: non-PPI INTID, unknown/zero frequency, inaccessible CNTV registers or unverified routing.
- Firmware services: firmware-configured counter access, described rather than assumed.
- Offline invariants: INTID in 16–31; nonzero bounded frequency; no enable when route is unknown.
- Hardware dependency: CNTFRQ and delivery evidence.

### 8. Primary CPU initialization

- Preconditions: resolved topology with one verified boot CPU; local GIC/timer ready.
- Inputs: boot MPIDR, logical mapping and cache topology.
- Output: one registered running processor.
- Failure: duplicate/missing MPIDR, boot CPU mismatch or unsupported topology.
- Firmware services: none.
- Offline invariants: one boot CPU, contiguous logical IDs, no secondary firmware call.
- Hardware dependency: resolved CPU topology.

### 9. Secondary CPU bring-up

- Preconditions: primary system stable; PSCI/conduit, secondary entry, coherency and per-CPU interrupt contracts all resolved.
- Inputs: secondary MPIDRs, physical entry, context identifiers and firmware adapter.
- Output: individually validated online processors.
- Failure: firmware error, timeout, wrong EL/reset state, coherency failure or SGI failure.
- Firmware services: validated PSCI `CPU_ON` or an evidenced replacement.
- Offline invariants: build-disabled while firmware contract is unknown; no hardcoded MPIDR pattern; error paths fail closed.
- Hardware dependency: every unresolved CPU/firmware item from Phase 2B.

## Reuse/replacement matrix

| Component | Decision | Boundary |
| --- | --- | --- |
| Host Mach-O/provenance tools | Directly reusable | No device dependency |
| Generic `_start`/`start_first_cpu` structure | Source modifications | Remove SWEET framebuffer; gate on entry contract |
| `boot_args` ABI | Configuration changes | Requires validated producer/ranges |
| `SweetPlatformExpert` / `xiaomi,sweet` | Replace | New WALLEYE identity and safe-node policy |
| `IODTPlatformExpert` nub mechanism | Source modifications | Reuse through constrained subclass |
| SWEET/Kryo 470 CPU driver | Replace | No topology/firmware assumption is portable |
| `ml_parse_cpu_topology` | Configuration changes | Reuse only with verified CPU records |
| GIC DT mapping/redistributor scan | Source modifications | Parameterize sizes, stride and policy |
| SWEET Group 1 IRQ path | Blocked | Security delivery unknown |
| ARM virtual-timer bookkeeping | Directly reusable | Only after external routing/frequency gates |
| SWEET framebuffer console | Replace | Address/geometry incompatible |
| UART | Blocked | Type/base/clock/readiness unknown |
| `arm_vm_init` and pmap | Source modifications | Valid ownership contract; no SWEET mapping |
| SWEET PSCI SMC path | Blocked | Conduit/EL/coherency unknown |

Common Qualcomm/GIC/UFS lineage is not a binary-compatibility argument.

## Critical blockers

- firmware entry and secondary-CPU contracts;
- exact MPIDR/cluster/cache topology;
- GIC region sizes, security ownership and ICC access;
- counter frequency and timer route;
- all missing reservation ranges and placements;
- safe physical placement and boot-argument/ADT producer;
- UART evidence.

Until these resolve, only compile-time skeletons and host models are appropriate. The plan deliberately contains no loader address and no boot-readiness state.
