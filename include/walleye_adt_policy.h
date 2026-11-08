/*
 * Pure compile-only WALLEYE normalized ADT policy interface.
 *
 * This API does not parse native Apple Device Tree bytes, publish IOKit
 * objects, initialize hardware, or establish boot compatibility.
 */
#ifndef WALLEYE_ADT_POLICY_H
#define WALLEYE_ADT_POLICY_H

#if !defined(__UINT8_TYPE__) || !defined(__UINT16_TYPE__) || !defined(__UINT32_TYPE__)
#error "compiler must provide fixed-width unsigned integer builtin types"
#endif

typedef __UINT8_TYPE__ walleye_adt_u8;
typedef __UINT16_TYPE__ walleye_adt_u16;
typedef __UINT32_TYPE__ walleye_adt_u32;

#define WALLEYE_ADT_POLICY_VERSION              1u
#define WALLEYE_ADT_MAX_NODES                   2u
#define WALLEYE_ADT_MAX_DEPTH                   1u
#define WALLEYE_ADT_MAX_PROPERTIES_PER_NODE     4u
#define WALLEYE_ADT_MAX_PROPERTY_SIZE           64u
#define WALLEYE_ADT_MAX_NORMALIZED_SIZE          4096u
#define WALLEYE_ADT_NO_PARENT                   ((walleye_adt_u16)0xffffu)

/* Stable result values. Structural validity never means boot readiness. */
typedef enum walleye_adt_result {
	WALLEYE_ADT_VALID_STRUCTURAL = 0,
	WALLEYE_ADT_INVALID_ARGUMENT = 1,
	WALLEYE_ADT_UNSUPPORTED_POLICY_VERSION = 2,
	WALLEYE_ADT_INVALID_STRUCTURE = 3,
	WALLEYE_ADT_BOUNDS_VIOLATION = 4,
	WALLEYE_ADT_DUPLICATE_DECLARATION = 5,
	WALLEYE_ADT_UNSUPPORTED_NODE = 6,
	WALLEYE_ADT_UNSUPPORTED_PROPERTY = 7,
	WALLEYE_ADT_INVALID_PROPERTY_VALUE = 8
} walleye_adt_result;

typedef enum walleye_adt_node_type {
	WALLEYE_ADT_NODE_ROOT = 1,
	WALLEYE_ADT_NODE_STRUCTURAL = 2,
	WALLEYE_ADT_NODE_HARDWARE = 3
} walleye_adt_node_type;

typedef enum walleye_adt_property_type {
	WALLEYE_ADT_PROPERTY_STRING = 1,
	WALLEYE_ADT_PROPERTY_STRING_LIST = 2,
	WALLEYE_ADT_PROPERTY_U32 = 3,
	WALLEYE_ADT_PROPERTY_U64 = 4,
	WALLEYE_ADT_PROPERTY_BOOLEAN = 5,
	WALLEYE_ADT_PROPERTY_DATA = 6
} walleye_adt_property_type;

/* A span is valid only when length <= capacity and data covers capacity bytes. */
typedef struct walleye_adt_span {
	const walleye_adt_u8 *data;
	walleye_adt_u32 length;
	walleye_adt_u32 capacity;
} walleye_adt_span;

typedef struct walleye_adt_node {
	walleye_adt_span path;
	walleye_adt_u16 parent_index;
	walleye_adt_u8 depth;
	walleye_adt_u8 node_type;
} walleye_adt_node;

typedef struct walleye_adt_property {
	walleye_adt_span name;
	walleye_adt_span value;
	walleye_adt_u16 node_index;
	walleye_adt_u8 property_type;
	walleye_adt_u8 reserved;
} walleye_adt_property;

#ifdef __cplusplus
extern "C" {
#endif

walleye_adt_result
walleye_validate_normalized_adt(
	walleye_adt_u32 policy_version,
	const walleye_adt_node *nodes,
	walleye_adt_u32 node_count,
	const walleye_adt_property *properties,
	walleye_adt_u32 property_count,
	walleye_adt_u32 normalized_size_bytes);

#ifdef __cplusplus
}
#endif

#endif /* WALLEYE_ADT_POLICY_H */
