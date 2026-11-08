/*
 * Compile-only board boundary for Google Pixel 2 (walleye), MSM8998.
 *
 * M1 deliberately contains no MMIO addresses, firmware calls, interrupt
 * setup, timer setup, diagnostic device, storage driver, or secondary-CPU
 * path.  Those interfaces remain unavailable until their contracts are
 * established by later milestones.
 */

#ifndef _PEXPERT_ARM64_WALLEYE_H
#define _PEXPERT_ARM64_WALLEYE_H

#define NO_MONITOR                1
#define NO_ECORE                  1

#define WALLEYE                   1
#define WALLEYE_COMPILE_ONLY      1

#define WALLEYE_ENABLE_PLATFORM_EXPERT  0
#define WALLEYE_ENABLE_FIRMWARE_CALLS   0
#define WALLEYE_ENABLE_SMP              0
#define WALLEYE_ENABLE_GIC              0
#define WALLEYE_ENABLE_TIMER            0
#define WALLEYE_ENABLE_UART             0
#define WALLEYE_ENABLE_FRAMEBUFFER      0
#define WALLEYE_ENABLE_STORAGE          0

#if WALLEYE_ENABLE_PLATFORM_EXPERT || WALLEYE_ENABLE_FIRMWARE_CALLS || \
    WALLEYE_ENABLE_SMP || WALLEYE_ENABLE_GIC || WALLEYE_ENABLE_TIMER || \
    WALLEYE_ENABLE_UART || WALLEYE_ENABLE_FRAMEBUFFER || \
    WALLEYE_ENABLE_STORAGE
#error "WALLEYE M1 is compile-only; hardware initialization must remain disabled"
#endif

/* Conservative architectural compile baseline; optional extensions omitted. */
#define __ARM_ARCH__              8
#define __ARM_VMSA__              8
#define __ARM_VFP__               4

#ifndef ASSEMBLER
#define PLATFORM_PANIC_LOG_DISABLED
#endif /* !ASSEMBLER */

#endif /* !_PEXPERT_ARM64_WALLEYE_H */
