# WALLEYE M1 compile-only build skeleton

## Scope and contents

M1 adds a separate `WALLEYE` machine configuration without implementing a platform driver:

- `patches/xnu/0001-walleye-build-skeleton.patch` adds the machine identifier, compiler flags, plain-arm64 selection, board-config boundary, `WALLEYE.h`, and `MASTER.arm64.walleye`;
- `overlays/walleye/` contains the independently inspectable new source files and compile probe;
- `config/walleye-build.json` is the machine-readable ISA, ABI, feature-gate, provenance and artifact manifest;
- `tools/validate_walleye_build.py` rejects configuration drift and SWEET dependencies;
- `tools/build_walleye_skeleton.py` checks source provenance and patch application, then compiles the largest available probe.

The board header defines every hardware-dependent gate as zero: Platform Expert, firmware calls, SMP, GIC, timer, UART, framebuffer and storage. There are no MMIO addresses, PSCI calls, device identity matches, or peripheral drivers.

## Source application boundary

The patch targets Apple XNU commit `1b191cb58250d0705d8a51287127505aa4bc0789` after ios-sweet patches `0001` through `0009`. Those prerequisites introduce the SWEET/open-source machine-layout files M1 extends. An offline path audit found that later SWEET patches do not modify `makedefs/MakeInc.def` or `pexpert/pexpert/arm64/board_config.h`; later edits to `MASTER.arm64.sweet` do not overlap the new `MASTER.arm64.walleye` file.

The real pinned worktree passed:

```text
git apply --check patches/xnu/0001-walleye-build-skeleton.patch
```

This validates source applicability only. It does not build or link XNU.

## Reproduction

Given an offline pinned tree with SWEET patches 0001–0009 applied:

```text
python3 tools/validate_walleye_build.py config/walleye-build.json
python3 tools/build_walleye_skeleton.py --source /path/to/pinned-xnu
python3 -m unittest discover -s tests -v
```

The script refuses the wrong XNU commit, a tree without the SWEET machine-config prerequisite, an already modified WALLEYE tree, or a patch that does not apply cleanly.

## Actual M1 build result

| Stage | Result | Meaning |
| --- | --- | --- |
| Machine-readable configuration validation | Passed | Manifest, flags, gates, hashes and source policy are internally consistent |
| Patch application | Passed | Patch applies to the pinned pre-M1 source boundary |
| XNU configuration utility | Not attempted | Apple build dependencies are unavailable |
| Freestanding host source compilation | Passed | `compile_probe.c` produced a host ELF object with Debian GCC 14.2.0 |
| ARM64 Mach-O source compilation | Unavailable | No Clang/ARM cross-compiler is installed in this executor |
| ARM64 object generation | Unavailable | No target object was fabricated |
| Linking | Not attempted | M1 intentionally defines no link target |
| Kernel build | Not attempted | Apple SDK/KDK and Xcode-era build tools remain unavailable |

The uncommitted host object was 1,128 bytes with SHA-256 `6fecb29a52be2f496e85bdeaf64eb4d8a6c8ee390f26b6232723147781923076`. Exact commands and input hashes are recorded in `evidence/walleye-m1-build.json` and `evidence/walleye-m1-build.log`. The object is a host-only validation artifact, not ARM64 code and not a kernel component.

## Remaining boundaries

M1 deliberately leaves Platform Expert implementation for M3 and retains every firmware, topology, memory-ownership, interrupt-security, timer-routing, diagnostic and storage unknown from Phase 2C. The configuration is not linked, bootable, flashable, or suitable for hardware execution.
