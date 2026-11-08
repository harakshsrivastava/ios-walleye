/* Compile-only probe for the post-M3A WALLEYE board policy. */
#include <pexpert/arm64/WALLEYE.h>

#if !defined(WALLEYE) || !WALLEYE_ENABLE_PLATFORM_EXPERT
#error "M3A must expose a distinct WALLEYE Platform Expert boundary"
#endif

#if WALLEYE_PLATFORM_EXPERT_START_SUPPORTED
#error "M3A must not enable runtime Platform Expert startup"
#endif

#if WALLEYE_ENABLE_FIRMWARE_CALLS || WALLEYE_ENABLE_SMP || \
    WALLEYE_ENABLE_GIC || WALLEYE_ENABLE_TIMER || \
    WALLEYE_ENABLE_UART || WALLEYE_ENABLE_FRAMEBUFFER || \
    WALLEYE_ENABLE_STORAGE
#error "M3A must not enable hardware-dependent paths"
#endif

extern "C" int
walleye_m3a_platform_expert_probe(void)
{
	return WALLEYE_COMPILE_ONLY ? 0 : 1;
}
