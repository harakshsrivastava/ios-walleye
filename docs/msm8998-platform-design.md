# MSM8998 offline platform-description design

## Purpose and boundary

`config/msm8998-platform.json` is a host-side evidence contract for Google Pixel 2 (`walleye`) hardware observations. It is not an Apple device tree, a bootloader configuration, an XNU Platform Expert implementation, or a claim that the SWEET kernel can boot. The validator performs no device access and does not calculate a load address.

The descriptor intentionally separates three states:

- known observations, each linked to a provenance record;
- derived facts, such as INTID 19 belonging to the PPI range;
- unknown or unavailable boot-time state, represented by null/`unknown` and reported as unresolved.

The source live FDT and original reservation list were unavailable during recovery. Accordingly, the descriptor preserves only the verified memory and reservation summary and does not invent the missing 15 static ranges or place the five dynamic reservations.

## Minimum abstraction interfaces

### CPU topology

The interface carries architecture and observed CPU count independently from topology. A future resolved form requires one ordered record per logical CPU, unique MPIDRs, contiguous logical IDs, cluster IDs and exactly one boot CPU. The current MPIDRs, cluster layout, boot CPU and performance classes remain unknown. This prevents importing SWEET's `0x000…0x700` Aff1 topology.

### GICv3

The interface records GICD base `0x17a00000`, GICR base `0x17b00000`, and redistributor stride `0x20000`. Region sizes, affinity enumeration, interrupt security ownership, and system-register-interface availability remain unresolved. A future consumer must not enable interrupts merely because the MMIO bases validate.

### Architectural timer

The interface supports the ARM virtual timer and validates that its INTID is a PPI (16–31). Walleye's reported INTID is 19. Counter frequency, routing, trigger/security configuration and firmware state remain unresolved.

### Diagnostics

UART and framebuffer are explicit optional interfaces with `unknown` status. Unknown interfaces must not contain a guessed type, base, clock or framebuffer address. In particular, SWEET's framebuffer address `0x9c000000` is not inherited.

### Physical and reserved memory

The only physical-memory declaration is `[0x80000000, 0x17e4c0000)`. It is validated for unsigned-64-bit bounds, ordering and page alignment. It is not labeled loader-safe. Resolved reservation records must be aligned, non-empty, within declared RAM and mutually non-overlapping. Unplaced dynamic reservations must contain no address. Summary-only inventory is accepted but produces unresolved findings for all unavailable placements.

### Firmware and boot interface

Initial exception level, PSCI version/conduit, CPU_ON support, secure-monitor contract, GIC ownership and runtime-versus-bootloader equivalence are null/unknown. The active Android slot and DTBO index are retained as historical observations, not handoff guarantees. Apple boot arguments and FDT-to-ADT translation are unresolved interfaces.

### Storage

The descriptor records UFS controller base `0x01da4000`, size `0x2500`, and PHY base `0x01da7000`. Region alignment, bounds, addition overflow and overlap are validated where sizes are known. PHY size, clocks, resets and firmware-left-link-up state remain unknown, so this is insufficient to initialize UFS.

## Validation model

`tools/validate_msm8998_platform.py` is dependency-free and returns:

- `invalid` when schema, ranges, topology, interrupt configuration, provenance or unknown-state invariants fail;
- `valid_with_unresolved` when known data is internally valid but required future evidence is explicitly absent;
- `valid` only if no error or unresolved condition remains.

It rejects missing required properties, booleans masquerading as integers, values outside unsigned 64-bit range, arithmetic overflow, reversed/empty ranges, misalignment, overlapping resolved reservation/MMIO ranges, reservations outside declared RAM, malformed CPU topology, non-PPI virtual-timer INTIDs, unsupported GIC/timer types, guessed values under an unknown status, and missing provenance.

Run it with:

```sh
python3 tools/validate_msm8998_platform.py config/msm8998-platform.json
```

The committed reference is expected to exit successfully with status `valid_with_unresolved`, not `valid`.

## Future XNU Platform Expert connection

A future integration can consume a validated, resolved descriptor through a translation stage rather than compile the JSON into the kernel directly:

1. Revalidate original boot artifacts and populate resolved CPU and reservation records.
2. Translate verified FDT nodes into a documented Apple-style device-tree contract.
3. Have a walleye-specific `IODTPlatformExpert` match an MSM8998/walleye identity and publish only validated nubs.
4. Feed GIC/timer properties to narrowly scoped interrupt/timer adapters; firmware security state must gate activation.
5. Register CPUs only after MPIDR, cluster and PSCI contracts resolve.
6. Enable a diagnostic or UFS provider only when its complete MMIO/clock/reset/firmware contract validates.

The translator should fail closed on unresolved required fields. Runtime observations must not be silently treated as bootloader-time guarantees.

## Current result

The documented walleye model passes with no errors and explicit unresolved conditions. This establishes an offline validation boundary only; it does not establish kernel, loader, firmware, storage or interrupt compatibility.
