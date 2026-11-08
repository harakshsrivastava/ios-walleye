#include "walleye_adt_policy.h"

#define WALLEYE_ADT_U32_MAX ((walleye_adt_u32)0xffffffffu)
#define WALLEYE_ADT_NODE_ACCOUNTING_SIZE 16u
#define WALLEYE_ADT_PROPERTY_ACCOUNTING_SIZE 24u

static int
walleye_add_u32(walleye_adt_u32 left, walleye_adt_u32 right,
    walleye_adt_u32 *result)
{
	if (right > WALLEYE_ADT_U32_MAX - left) {
		return 0;
	}
	*result = left + right;
	return 1;
}

static int
walleye_mul_u32(walleye_adt_u32 left, walleye_adt_u32 right,
    walleye_adt_u32 *result)
{
	if (left != 0u && right > WALLEYE_ADT_U32_MAX / left) {
		return 0;
	}
	*result = left * right;
	return 1;
}

static walleye_adt_result
walleye_span_check(const walleye_adt_span *span)
{
	if (span->length > span->capacity) {
		return WALLEYE_ADT_BOUNDS_VIOLATION;
	}
	if (span->capacity != 0u && span->data == (const walleye_adt_u8 *)0) {
		return WALLEYE_ADT_INVALID_ARGUMENT;
	}
	return WALLEYE_ADT_VALID_STRUCTURAL;
}

static int
walleye_span_equal_bytes(const walleye_adt_span *span,
    const walleye_adt_u8 *bytes, walleye_adt_u32 length)
{
	walleye_adt_u32 index;

	if (span->length != length || (length != 0u && span->data == (const walleye_adt_u8 *)0)) {
		return 0;
	}
	for (index = 0u; index < length; index++) {
		if (span->data[index] != bytes[index]) {
			return 0;
		}
	}
	return 1;
}

static int
walleye_span_equal(const walleye_adt_span *left,
    const walleye_adt_span *right)
{
	walleye_adt_u32 index;

	if (left->length != right->length) {
		return 0;
	}
	for (index = 0u; index < left->length; index++) {
		if (left->data[index] != right->data[index]) {
			return 0;
		}
	}
	return 1;
}

static walleye_adt_result
walleye_account_span(const walleye_adt_span *span, walleye_adt_u32 *size)
{
	walleye_adt_result result = walleye_span_check(span);

	if (result != WALLEYE_ADT_VALID_STRUCTURAL) {
		return result;
	}
	if (!walleye_add_u32(*size, span->length, size)) {
		return WALLEYE_ADT_BOUNDS_VIOLATION;
	}
	return WALLEYE_ADT_VALID_STRUCTURAL;
}

walleye_adt_result
walleye_validate_normalized_adt(
    walleye_adt_u32 policy_version,
    const walleye_adt_node *nodes,
    walleye_adt_u32 node_count,
    const walleye_adt_property *properties,
    walleye_adt_u32 property_count,
    walleye_adt_u32 normalized_size_bytes)
{
	static const walleye_adt_u8 root_path[] = {'/'};
	static const walleye_adt_u8 chosen_path[] = {'/', 'c', 'h', 'o', 's', 'e', 'n'};
	static const walleye_adt_u8 name_key[] = {'n', 'a', 'm', 'e'};
	static const walleye_adt_u8 root_name[] = {
		'd', 'e', 'v', 'i', 'c', 'e', '-', 't', 'r', 'e', 'e'
	};
	static const walleye_adt_u8 chosen_name[] = {'c', 'h', 'o', 's', 'e', 'n'};
	walleye_adt_u32 logical_size;
	walleye_adt_u32 partial;
	walleye_adt_u32 node_index;
	walleye_adt_u32 property_index;
	walleye_adt_u32 other_index;
	walleye_adt_u32 root_count = 0u;
	walleye_adt_u32 chosen_count = 0u;
	walleye_adt_u32 name_count[WALLEYE_ADT_MAX_NODES] = {0u, 0u};
	walleye_adt_result result;

	if ((node_count != 0u && nodes == (const walleye_adt_node *)0) ||
	    (property_count != 0u && properties == (const walleye_adt_property *)0)) {
		return WALLEYE_ADT_INVALID_ARGUMENT;
	}
	if (policy_version != WALLEYE_ADT_POLICY_VERSION) {
		return WALLEYE_ADT_UNSUPPORTED_POLICY_VERSION;
	}
	if (node_count == 0u) {
		return WALLEYE_ADT_INVALID_STRUCTURE;
	}
	if (node_count > WALLEYE_ADT_MAX_NODES ||
	    property_count > WALLEYE_ADT_MAX_NODES * WALLEYE_ADT_MAX_PROPERTIES_PER_NODE) {
		return WALLEYE_ADT_BOUNDS_VIOLATION;
	}
	if (normalized_size_bytes > WALLEYE_ADT_MAX_NORMALIZED_SIZE) {
		return WALLEYE_ADT_BOUNDS_VIOLATION;
	}
	if (!walleye_mul_u32(node_count, WALLEYE_ADT_NODE_ACCOUNTING_SIZE, &logical_size) ||
	    !walleye_mul_u32(property_count, WALLEYE_ADT_PROPERTY_ACCOUNTING_SIZE, &partial) ||
	    !walleye_add_u32(logical_size, partial, &logical_size)) {
		return WALLEYE_ADT_BOUNDS_VIOLATION;
	}

	for (node_index = 0u; node_index < node_count; node_index++) {
		result = walleye_account_span(&nodes[node_index].path, &logical_size);
		if (result != WALLEYE_ADT_VALID_STRUCTURAL) {
			return result;
		}
		if (nodes[node_index].depth > WALLEYE_ADT_MAX_DEPTH) {
			return WALLEYE_ADT_BOUNDS_VIOLATION;
		}
		if (nodes[node_index].path.length == 0u || nodes[node_index].path.data[0] != (walleye_adt_u8)'/') {
			return WALLEYE_ADT_INVALID_STRUCTURE;
		}
		if (walleye_span_equal_bytes(&nodes[node_index].path, root_path, 1u)) {
			root_count++;
			if (nodes[node_index].node_type != WALLEYE_ADT_NODE_ROOT ||
			    nodes[node_index].depth != 0u ||
			    nodes[node_index].parent_index != WALLEYE_ADT_NO_PARENT) {
				return WALLEYE_ADT_INVALID_STRUCTURE;
			}
		} else if (walleye_span_equal_bytes(&nodes[node_index].path, chosen_path, 7u)) {
			chosen_count++;
			if (nodes[node_index].node_type != WALLEYE_ADT_NODE_STRUCTURAL ||
			    nodes[node_index].depth != 1u ||
			    nodes[node_index].parent_index >= node_count ||
			    !walleye_span_equal_bytes(&nodes[nodes[node_index].parent_index].path,
			    root_path, 1u)) {
				return WALLEYE_ADT_INVALID_STRUCTURE;
			}
		} else {
			return WALLEYE_ADT_UNSUPPORTED_NODE;
		}
		for (other_index = 0u; other_index < node_index; other_index++) {
			if (walleye_span_equal(&nodes[node_index].path, &nodes[other_index].path)) {
				return WALLEYE_ADT_DUPLICATE_DECLARATION;
			}
		}
	}
	if (root_count != 1u || chosen_count > 1u || nodes[0].parent_index != WALLEYE_ADT_NO_PARENT ||
	    !walleye_span_equal_bytes(&nodes[0].path, root_path, 1u)) {
		return WALLEYE_ADT_INVALID_STRUCTURE;
	}

	for (property_index = 0u; property_index < property_count; property_index++) {
		const walleye_adt_property *property = &properties[property_index];

		result = walleye_account_span(&property->name, &logical_size);
		if (result != WALLEYE_ADT_VALID_STRUCTURAL) {
			return result;
		}
		result = walleye_account_span(&property->value, &logical_size);
		if (result != WALLEYE_ADT_VALID_STRUCTURAL) {
			return result;
		}
		if (property->reserved != 0u || property->node_index >= node_count) {
			return WALLEYE_ADT_INVALID_STRUCTURE;
		}
		if (property->property_type != WALLEYE_ADT_PROPERTY_STRING) {
			return WALLEYE_ADT_UNSUPPORTED_PROPERTY;
		}
		if (property->value.length > WALLEYE_ADT_MAX_PROPERTY_SIZE) {
			return WALLEYE_ADT_BOUNDS_VIOLATION;
		}
		if (!walleye_span_equal_bytes(&property->name, name_key, 4u)) {
			return WALLEYE_ADT_UNSUPPORTED_PROPERTY;
		}
		for (other_index = 0u; other_index < property_index; other_index++) {
			if (properties[other_index].node_index == property->node_index &&
			    walleye_span_equal(&properties[other_index].name, &property->name)) {
				return WALLEYE_ADT_DUPLICATE_DECLARATION;
			}
		}
		name_count[property->node_index]++;
		if (name_count[property->node_index] > WALLEYE_ADT_MAX_PROPERTIES_PER_NODE) {
			return WALLEYE_ADT_BOUNDS_VIOLATION;
		}
		if (walleye_span_equal_bytes(&nodes[property->node_index].path, root_path, 1u)) {
			if (!walleye_span_equal_bytes(&property->value, root_name, 11u)) {
				return WALLEYE_ADT_INVALID_PROPERTY_VALUE;
			}
		} else if (!walleye_span_equal_bytes(&property->value, chosen_name, 6u)) {
			return WALLEYE_ADT_INVALID_PROPERTY_VALUE;
		}
	}
	for (node_index = 0u; node_index < node_count; node_index++) {
		if (name_count[node_index] != 1u) {
			return WALLEYE_ADT_INVALID_STRUCTURE;
		}
	}
	if (logical_size != normalized_size_bytes) {
		return WALLEYE_ADT_BOUNDS_VIOLATION;
	}
	return WALLEYE_ADT_VALID_STRUCTURAL;
}
