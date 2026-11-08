/* Host/target compile probe for the M1 WALLEYE board boundary. */
#include <pexpert/arm64/WALLEYE.h>

#if !defined(WALLEYE) || !defined(WALLEYE_COMPILE_ONLY)
#error "WALLEYE compile-only identity is missing"
#endif

#if WALLEYE_ENABLE_PLATFORM_EXPERT || WALLEYE_ENABLE_FIRMWARE_CALLS || \
    WALLEYE_ENABLE_SMP || WALLEYE_ENABLE_GIC || WALLEYE_ENABLE_TIMER || \
    WALLEYE_ENABLE_UART || WALLEYE_ENABLE_FRAMEBUFFER || \
    WALLEYE_ENABLE_STORAGE
#error "M1 must not enable a hardware-dependent path"
#endif

#if defined(__ARM_V8_CRYPTO_EXTENSIONS__) || defined(__ARM_PAN_AVAILABLE__)
#error "Unverified optional architectural features leaked into WALLEYE"
#endif

#if defined(__ARM_16K_PG__)
#error "The 16 KiB runtime page-granule contract is not established"
#endif

int
walleye_m1_compile_probe(void)
{
	return (__ARM_ARCH__ == 8 && __ARM_VMSA__ == 8 && __ARM_VFP__ == 4) ? 0 : 1;
}
