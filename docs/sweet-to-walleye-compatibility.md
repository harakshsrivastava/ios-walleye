# SWEET-to-walleye compatibility assessment

This comparison uses only the recovered walleye evidence and the verified SWEET binary/source. “Potentially reusable” means suitable for further engineering review, not boot compatible.

| Component | SWEET finding | Walleye evidence | Classification | Required work / uncertainty |
| --- | --- | --- | --- | --- |
| Mach-O container/parser | Standard little-endian ARM64 `MH_EXECUTE`, symbol and relocation tables | ARM64 target | Architecture-generic and potentially reusable | Loader contract and physical placement remain unknown. |
| XNU ARM64 core | Plain ARM64 kernel, no arm64e/PAC; built `-march=armv8.2-a+crypto` | Snapdragon 835/MSM8998, eight ARM64 CPUs | Qualcomm-specific but requires adaptation | Audit ARMv8.2 instruction use against Kryo 280 capabilities; do not assume the binary ISA is accepted. |
| Page tables/memory | SWEET config forces 16 KiB pages and large-memory physmap changes | FDT RAM `0x80000000–0x17e4c0000`; 20 reserved-memory children | Unknown or unsupported by available evidence | Reconcile reservations and boot allocations; RAM declaration is not a safe loader range. |
| Platform Expert | DT-based `SweetPlatformExpert`; matches `xiaomi,sweet`; product is Redmi Note 10 Pro | MSM8998-compatible live FDT | SWEET-specific and incompatible | Implement a walleye platform match and verified property translation; remove product identity assumptions. |
| CPU topology | Up to 8 cores; six A55 + two A76 treated homogeneous; MPIDRs expected `0x000…0x700` in Aff1; boot CPU 0 | Eight ARM64 Kryo 280 cores; no recovered MPIDR/topology proof | SWEET-specific and incompatible | Derive walleye MPIDRs, clusters, cache topology and performance classes from evidence. |
| GICv3 distributor | DT-discovered `/arm-io/gic`; Group 1 non-secure path | GICD `0x17a00000` | Qualcomm-specific but requires adaptation | Address aligns conceptually only; verify DT format, security grouping and ownership. |
| GICv3 redistributors | DT-discovered base/size; stride `0x20000`; SGI 1 | GICR `0x17b00000`, stride `0x20000` | Qualcomm-specific but requires adaptation | Strong structural match, but per-CPU affinity discovery and firmware state remain unverified. |
| Virtual timer | Architected CNTV timer, default INTID 19, DT-overridable | Virtual timer INTID 19 | Architecture-generic and potentially reusable | Verify counter frequency, PPI routing and non-secure Group 1 delivery on MSM8998. |
| Early interrupt path | Reads `ICC_IAR1_EL1`; timers/IPIs/other IRQs share IRQ path | No recovered security-state evidence | Unknown or unsupported by available evidence | TrustZone interrupt ownership and ICC system-register access must be measured from documentation/artifacts. |
| SMP firmware | PSCI CPU_ON via SMC64 function `0xC4000003`; secondary EL2-to-EL1 setup | No recovered PSCI/conduit or handoff-EL evidence | Unknown or unsupported by available evidence | Establish PSCI version/conduit, entry constraints, EL, reset state and coherency protocol. |
| UART/early diagnostics | Device UART considered unusable; early output uses framebuffer at hardcoded `0x9c000000` | Samsung S6E3FA5 panel; no verified framebuffer address/geometry | SWEET-specific and incompatible | Replace with a proven walleye diagnostic sink; never reuse the framebuffer address. |
| UFS host | Polled UFSHCI, firmware-left-link-up assumption, custom `/sweet-ufs` node | UFS controller `0x01da4000` size `0x2500`; PHY `0x01da7000`; Samsung 64 GB | Qualcomm-specific but requires adaptation | Build MSM8998 register/PHY/clock/reset contract; do not infer compatibility from UFSHCI alone. |
| Boot arguments / DT | Expects Apple boot args and transformed ADT nodes (`/arm-io/gic`, `/sweet-ufs`, `sweet-fbcon`, CPU properties) | Linux FDT reconciled to stock entry 3, but no Apple handoff artifact survived | Qualcomm-specific but requires adaptation | A validated FDT-to-ADT/handoff contract is still required. |
| Secure monitor | Board says `NO_MONITOR`, yet PSCI uses `smc #0`; GIC assumes TrustZone owns Group 0 | MSM8998 secure-world interfaces not recovered | Unknown or unsupported by available evidence | Document and validate firmware services without probing hardware in this phase. |
| SWEET peripherals | Hardcoded display, touch, PMIC and USB addresses in later patches | Different SoC/device | SWEET-specific and incompatible | Exclude from walleye baseline. |

## Concrete shared evidence

The strongest commonality is GICv3 plus a `0x20000` redistributor stride and virtual timer INTID 19. These are useful design inputs but not proof that the SWEET interrupt implementation can be reused unchanged. UFS is similarly a shared Qualcomm/UFSHCI concept with incompatible controller integration details.

## Blocking unknowns

Before any walleye kernel handoff can be evaluated, evidence is still needed for the boot CPU MPIDR and cluster layout, supported architectural ISA features, initial exception level, PSCI conduit/version, GIC security configuration, counter frequency, Apple boot-argument/ADT layout, safe loader allocations after all reservations, and MSM8998 UFS clock/reset/PHY state. No finding here establishes boot compatibility.
