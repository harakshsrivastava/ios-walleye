# SWEET reference-kernel analysis

## Scope and provenance

This is static, offline analysis only. Nothing was executed, patched, booted, or sent to hardware. The input was `kernel.development.sweet` from `dipa-studio/ios-sweet` GitHub Actions workflow `xnu`, run 94 (run ID `39158169212`, head `fdad0de8dc0e75c5ea84762adc03f7232dc91f19`, artifact ID `12147422947`). The retained artifact ZIP hashes to `28a040196aa632af45b7ba6415831a09dd5098f7f9338b5ce6d1c146a9982b56`; the kernel hashes to the expected `d9cb893bd2baf841e94cd2001f0ec70c0fea42f045f87f14ae807e4ebc50e1e5`. The source comparison used `ios-sweet` commit `45263bee51df4a0f55cdf9c649af886399488ddb`, its 81 patches, and Apple XNU `1b191cb58250d0705d8a51287127505aa4bc0789` (`xnu-8796.141.3`). The binary is deliberately not committed.

## Mach-O structure

The bounded parser reports little-endian 64-bit Mach-O, CPU type ARM64, subtype 0, file type `MH_EXECUTE`, 26 load commands occupying 5,608 bytes, UUID `ddd06a9e-ed50-3454-991a-5972ae4cc949`, and flags `0x00200001` (`MH_NOUNDEFS | MH_PIE`). `LC_BUILD_VERSION` says platform 1 with minimum/SDK value `0x000e0000` (14.0); this is build metadata, not an assertion that the kernel is a macOS userland executable.

There are 19 `LC_SEGMENT_64` commands and 47 sections. File-backed content spans the complete 17,206,064-byte file. The principal mapped ranges are:

| Segment | VM range | File range | Meaning |
| --- | --- | --- | --- |
| `__TEXT` | `0xfffffe0007004000–0xfffffe0007164000` | `0–0x160000` | constants, C strings, logs, vectors |
| `__DATA_CONST` | `0xfffffe0007164000–0xfffffe00072e4000` | `0x160000–0x2e0000` | immutable data and init pointers |
| `__TEXT_EXEC` | `0xfffffe00072e4000–0xfffffe0007b38000` | `0x2e0000–0xb34000` | executable kernel text |
| `__DATA` | `0xfffffe0007b44000–0xfffffe0008078000` | `0xb40000–0xb88000` plus zero-fill | writable, per-CPU, common and BSS data |
| `__BOOTDATA` | `0xfffffe0008078000–0xfffffe00080c4000` | `0xb88000–0xbd4000` | boot initialization data |
| `__LINKINFO` | `0xfffffe00080c4000–0xfffffe0008110000` | `0xbd4000–0xc20000` | symbol-set metadata |
| `__LINKEDIT` | `0xfffffe0008110000–0xfffffe00084c4b30` | `0xcb4000–0x1064b30` | symbols and relocations |

The zero-sized prelink segments show no embedded prelinked kext payload. Exact segment records are in `config/sweet-kernel-reference.json`; the parser emits every section with offsets, sizes, protections, flags, and relocation fields.

## Entry and loader assumptions

There is no `LC_MAIN`. `LC_UNIXTHREAD` sets PC to `0xfffffe000748b488`, exactly symbol `__start`, in `__TEXT_EXEC` at file offset `0x487488`; initial SP is zero and CPSR is zero. Therefore this is a kernel-style handoff, not a process entry contract. The loader must map the image as XNU expects and supply the register/boot-argument environment from which early assembly establishes usable execution state. SP=0 must not be interpreted as a callable C entry. This analysis does not determine safe physical load addresses or prove the required boot-argument layout.

## Symbols, relocations and fixups

`LC_SYMTAB` contains 70,853 symbols, all named. SWEET evidence includes `SweetPlatformExpert`, `SweetCPU`, framebuffer console, UFS, GIC base variables, PRNG and other platform additions. `LC_DYSYMTAB` declares 77,056 local relocations and zero external relocations. All section relocation counts are zero. There is no `LC_DYLD_INFO_ONLY`, `LC_DYLD_CHAINED_FIXUPS`, rebase/bind stream, or chained-fixup payload. These facts describe this linked artifact; they do not by themselves establish whether a particular boot loader must apply slide/static relocation processing.

## Version, strings and device-tree contracts

The embedded version is `Darwin Kernel Version 22.6.0: Mon Aug 14 05:06:07 UTC 2023; runner:xnu-8796.141.3`. Relevant strings and symbols include `/arm-io/gic`, `/sweet-ufs`, `sweet-fbcon`, `Kryo 470`, `virtual-timer-intid`, `ufsroot`, `cpus`, and `cpumask`. No dedicated embedded-device-tree section was found. Platform code instead consumes an Apple-style device tree supplied at boot.

The source establishes these contracts:

- `0004`: adds the plain-ARM64, ARMv8.2+crypto, 16 KiB-page SWEET machine configuration; routes non-secure Group 1 GICv3 interrupts through `sleh_irq`; uses virtual timer INTID 19 and SGI 1 defaults.
- `0016`: installs `SweetPlatformExpert`, matching `xiaomi,sweet`, publishes DT nubs, omits Apple NVRAM assumptions, and returns product `Redmi Note 10 Pro`.
- `0017`: permits DT property `virtual-timer-intid` to override the timer PPI after range validation.
- `0018`, `0065`, `0078`: match `qcom,kryo470`; bring CPUs up with PSCI `CPU_ON` (`0xC4000003`, `smc #0`); assume boot CPU logical/MPIDR zero, ascending MPIDRs in Aff1, one logical cluster, and up to eight SWEET cores. Patch 78 treats six A55 and two A76 cores as homogeneous.
- `0003`, `0010`, `0012`: use a DT-described `sweet-fbcon`, while early diagnostics also hardcode framebuffer physical address `0x9c000000` and SWEET display geometry.
- `0028`, `0034`: implement a polled Qualcomm UFSHCI path discovered through `/sweet-ufs`; it assumes firmware left the controller enabled with its link up and uses a contiguous DMA/bounce region.
- `0065`: depends on PSCI/SMCCC and contains secondary-entry EL2 setup, including constant `0x30d00800`. The board config defines `NO_MONITOR`, but this does not eliminate the firmware dependency used by PSCI.

Other later patches contain SWEET peripheral MMIO constants for touch/keys, PMIC/display and USB. They are platform drivers, not generic evidence for walleye, and must not be transplanted by address.

## Limitations

Static inspection cannot establish firmware behavior, actual DT contents, EL at handoff, cache/coherency state, memory reservations, interrupt security ownership, UFS link state, or successful execution on either device. CTF was present as a section but was not semantically decoded. No disassembler was installed; entry identity was established from the exact symbol address and Mach-O metadata rather than instruction-level control-flow recovery.
