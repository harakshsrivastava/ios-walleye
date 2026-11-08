# WALLEYE conservative ISA baseline

## Decision

M1 compiles the WALLEYE boundary as plain AArch64 with the base Armv8-A ISA:

- standalone validation triple: `arm64-apple-darwin22`;
- architecture flags: `-march=armv8-a -mno-outline-atomics`;
- CPU-specific flags: none;
- XNU machine definition: `-DARM64_BOARD_CONFIG_WALLEYE`;
- Mach-O architecture when a suitable compiler is available: `arm64`, never `arm64e`.

This is a conservative code-generation policy, not a claim that the available evidence inventories every Kryo 280 feature. The recovered evidence establishes eight ARM64 CPUs and the Phase 3 target identifies MSM8998/Kryo 280. It does not contain CPU ID registers or a complete optional-extension inventory. Base Armv8-A is therefore the smallest defensible compiler contract. `-mno-outline-atomics` prevents an implicit LSE/runtime-dispatch dependency from entering this freestanding target.

## SWEET audit

Direct inspection of ios-sweet patch `0004-sweet-machine-config.patch` at commit `45263bee51df4a0f55cdf9c649af886399488ddb` found:

- `-march=armv8.2-a+crypto`;
- plain `arm64` selected specifically for SWEET;
- Kryo 470 / Cortex-A76 / Cortex-A55 assumptions;
- `__ARM_V8_CRYPTO_EXTENSIONS__`, `__ARM_PAN_AVAILABLE__`, and `__ARM_16K_PG__`;
- `HAS_GIC_V3`, `ARM_ARCH_TIMER`, timer INTID, SGI, and redistributor declarations.

WALLEYE carries none of those optional CPU or hardware declarations. This does not prove that MSM8998 lacks every extension; it means they are not admitted without target evidence. In particular, ARMv8.2, crypto code generation, PAN, LSE, pointer authentication, and a 16 KiB translation granule are outside the M1 contract.

## ABI assumptions and limits

The compile boundary assumes AArch64, LP64, little-endian, freestanding kernel code and no pointer authentication. Omitting `__ARM_16K_PG__` makes this skeleton use XNU's 4 KiB compile default. That is only enough to validate configuration/header compilation; runtime page-granule suitability and iOS userland compatibility remain unresolved.

`MAX_CPUS=1` is a fail-closed compile limit, not a statement that the phone has one CPU. It prevents M1 from exposing the unresolved secondary-CPU path. `MAX_L2_CLINE=7` is a conservative compile-time capacity, not a measured cache-line claim. No PMU provider is enabled.

## Provenance classification

| Item | Evidence status | Source |
| --- | --- | --- |
| Eight ARM64 CPUs | Historical report | `config/msm8998-platform.json` |
| MSM8998/Kryo 280 target | Project target | Phase 3 task and repository platform identity |
| SWEET ARMv8.2+crypto flags | Direct source | ios-sweet patch 0004 at the pinned commit |
| WALLEYE Armv8-A selection | Conservative policy | Phase 2C prohibition on carrying the SWEET ISA assumption |
| Optional Kryo 280 features | Unknown | CPU ID/feature-register evidence unavailable |
| Runtime page granule | Unknown | Firmware/MMU contract unavailable |

No part of this decision establishes an exception-level, MMU, cache, firmware, or boot contract.
