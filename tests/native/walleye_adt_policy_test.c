#include <stdio.h>
#include <string.h>

#include "walleye_adt_policy.h"

typedef struct test_fixture {
	walleye_adt_node nodes[3];
	walleye_adt_property properties[9];
	walleye_adt_u32 node_count;
	walleye_adt_u32 property_count;
} test_fixture;

static const walleye_adt_u8 root_path[] = {'/'};
static const walleye_adt_u8 chosen_path[] = {'/', 'c', 'h', 'o', 's', 'e', 'n'};
static const walleye_adt_u8 bad_path[] = {'m', 'i', 's', 's', 'i', 'n', 'g'};
static const walleye_adt_u8 unknown_path[] = {'/', 'm', 'y', 's', 't', 'e', 'r', 'y'};
static const walleye_adt_u8 gpu_path[] = {'/', 'g', 'p', 'u'};
static const walleye_adt_u8 name_key[] = {'n', 'a', 'm', 'e'};
static const walleye_adt_u8 compatible_key[] = {
	'c', 'o', 'm', 'p', 'a', 't', 'i', 'b', 'l', 'e'
};
static const walleye_adt_u8 root_name[] = {
	'd', 'e', 'v', 'i', 'c', 'e', '-', 't', 'r', 'e', 'e'
};
static const walleye_adt_u8 chosen_name[] = {'c', 'h', 'o', 's', 'e', 'n'};
static const walleye_adt_u8 bad_name[] = {'s', 'w', 'e', 'e', 't'};
static const walleye_adt_u8 sweet_identity[] = {
	'x', 'i', 'a', 'o', 'm', 'i', ',', 's', 'w', 'e', 'e', 't'
};
static const walleye_adt_u8 oversized_value[65] = {0};

static walleye_adt_span
span(const walleye_adt_u8 *data, walleye_adt_u32 length)
{
	walleye_adt_span value;
	value.data = data;
	value.length = length;
	value.capacity = length;
	return value;
}

static void
initialize_valid(test_fixture *fixture, int include_chosen)
{
	(void)memset(fixture, 0, sizeof(*fixture));
	fixture->nodes[0].path = span(root_path, 1u);
	fixture->nodes[0].parent_index = WALLEYE_ADT_NO_PARENT;
	fixture->nodes[0].depth = 0u;
	fixture->nodes[0].node_type = WALLEYE_ADT_NODE_ROOT;
	fixture->properties[0].name = span(name_key, 4u);
	fixture->properties[0].value = span(root_name, 11u);
	fixture->properties[0].node_index = 0u;
	fixture->properties[0].property_type = WALLEYE_ADT_PROPERTY_STRING;
	fixture->node_count = 1u;
	fixture->property_count = 1u;
	if (include_chosen) {
		fixture->nodes[1].path = span(chosen_path, 7u);
		fixture->nodes[1].parent_index = 0u;
		fixture->nodes[1].depth = 1u;
		fixture->nodes[1].node_type = WALLEYE_ADT_NODE_STRUCTURAL;
		fixture->properties[1].name = span(name_key, 4u);
		fixture->properties[1].value = span(chosen_name, 6u);
		fixture->properties[1].node_index = 1u;
		fixture->properties[1].property_type = WALLEYE_ADT_PROPERTY_STRING;
		fixture->node_count = 2u;
		fixture->property_count = 2u;
	}
}

static walleye_adt_u32
logical_size(const test_fixture *fixture)
{
	walleye_adt_u32 index;
	walleye_adt_u32 size = fixture->node_count * 16u + fixture->property_count * 24u;
	for (index = 0u; index < fixture->node_count && index < 3u; index++) {
		size += fixture->nodes[index].path.length;
	}
	for (index = 0u; index < fixture->property_count && index < 9u; index++) {
		size += fixture->properties[index].name.length;
		size += fixture->properties[index].value.length;
	}
	return size;
}

static walleye_adt_result
validate(const test_fixture *fixture)
{
	return walleye_validate_normalized_adt(
		WALLEYE_ADT_POLICY_VERSION,
		fixture->nodes,
		fixture->node_count,
		fixture->properties,
		fixture->property_count,
		logical_size(fixture));
}

static int
expect(const char *name, walleye_adt_result actual, walleye_adt_result expected)
{
	if (actual != expected) {
		(void)fprintf(stderr, "%s: got %d expected %d\n", name, (int)actual, (int)expected);
		return 1;
	}
	return 0;
}

int
main(void)
{
	test_fixture fixture;
	int failures = 0;

	initialize_valid(&fixture, 0);
	failures += expect("root only", validate(&fixture), WALLEYE_ADT_VALID_STRUCTURAL);
	initialize_valid(&fixture, 1);
	failures += expect("root and chosen", validate(&fixture), WALLEYE_ADT_VALID_STRUCTURAL);

	initialize_valid(&fixture, 0);
	fixture.node_count = 0u;
	fixture.property_count = 0u;
	failures += expect("missing root", validate(&fixture), WALLEYE_ADT_INVALID_STRUCTURE);

	initialize_valid(&fixture, 0);
	fixture.nodes[1] = fixture.nodes[0];
	fixture.node_count = 2u;
	failures += expect("duplicate root", validate(&fixture), WALLEYE_ADT_DUPLICATE_DECLARATION);

	initialize_valid(&fixture, 1);
	fixture.nodes[2] = fixture.nodes[1];
	fixture.node_count = 3u;
	failures += expect("duplicate chosen exceeds node bound", validate(&fixture), WALLEYE_ADT_BOUNDS_VIOLATION);

	initialize_valid(&fixture, 1);
	fixture.nodes[1].path = span(unknown_path, 8u);
	failures += expect("unknown node", validate(&fixture), WALLEYE_ADT_UNSUPPORTED_NODE);

	initialize_valid(&fixture, 0);
	fixture.properties[0].name = span(compatible_key, 10u);
	failures += expect("unknown property", validate(&fixture), WALLEYE_ADT_UNSUPPORTED_PROPERTY);

	initialize_valid(&fixture, 0);
	fixture.properties[0].name = span(compatible_key, 10u);
	fixture.properties[0].value = span(sweet_identity, 12u);
	failures += expect("sweet identity", validate(&fixture), WALLEYE_ADT_UNSUPPORTED_PROPERTY);

	initialize_valid(&fixture, 0);
	fixture.properties[0].value = span(bad_name, 5u);
	failures += expect("invalid root name", validate(&fixture), WALLEYE_ADT_INVALID_PROPERTY_VALUE);

	initialize_valid(&fixture, 1);
	fixture.properties[1].value = span(bad_name, 5u);
	failures += expect("invalid chosen name", validate(&fixture), WALLEYE_ADT_INVALID_PROPERTY_VALUE);

	initialize_valid(&fixture, 0);
	fixture.properties[0].value = span(oversized_value, 65u);
	failures += expect("oversized property", validate(&fixture), WALLEYE_ADT_BOUNDS_VIOLATION);

	initialize_valid(&fixture, 0);
	failures += expect("oversized fixture",
		walleye_validate_normalized_adt(1u, fixture.nodes, 1u, fixture.properties, 1u, 4097u),
		WALLEYE_ADT_BOUNDS_VIOLATION);

	initialize_valid(&fixture, 1);
	fixture.nodes[1].depth = 2u;
	failures += expect("excessive depth", validate(&fixture), WALLEYE_ADT_BOUNDS_VIOLATION);

	initialize_valid(&fixture, 0);
	fixture.nodes[0].path = span(bad_path, 7u);
	failures += expect("invalid path", validate(&fixture), WALLEYE_ADT_INVALID_STRUCTURE);

	initialize_valid(&fixture, 0);
	fixture.properties[0].property_type = WALLEYE_ADT_PROPERTY_U32;
	failures += expect("invalid property type", validate(&fixture), WALLEYE_ADT_UNSUPPORTED_PROPERTY);

	initialize_valid(&fixture, 0);
	fixture.properties[0].value.data = (const walleye_adt_u8 *)0;
	failures += expect("null pointer nonzero length", validate(&fixture), WALLEYE_ADT_INVALID_ARGUMENT);

	initialize_valid(&fixture, 0);
	fixture.properties[0].value.capacity = 5u;
	failures += expect("truncated value", validate(&fixture), WALLEYE_ADT_BOUNDS_VIOLATION);

	initialize_valid(&fixture, 0);
	failures += expect("integer/count overflow",
		walleye_validate_normalized_adt(1u, fixture.nodes, (walleye_adt_u32)0xffffffffu,
		fixture.properties, 1u, logical_size(&fixture)), WALLEYE_ADT_BOUNDS_VIOLATION);

	initialize_valid(&fixture, 1);
	fixture.nodes[1].parent_index = 1u;
	failures += expect("invalid parent", validate(&fixture), WALLEYE_ADT_INVALID_STRUCTURE);

	initialize_valid(&fixture, 0);
	failures += expect("unsupported version",
		walleye_validate_normalized_adt(2u, fixture.nodes, 1u, fixture.properties, 1u,
		logical_size(&fixture)), WALLEYE_ADT_UNSUPPORTED_POLICY_VERSION);

	initialize_valid(&fixture, 0);
	fixture.properties[1] = fixture.properties[0];
	fixture.property_count = 2u;
	failures += expect("duplicate property", validate(&fixture), WALLEYE_ADT_DUPLICATE_DECLARATION);

	initialize_valid(&fixture, 0);
	fixture.property_count = 0u;
	failures += expect("missing name", validate(&fixture), WALLEYE_ADT_INVALID_STRUCTURE);

	initialize_valid(&fixture, 0);
	fixture.properties[0].node_index = 1u;
	failures += expect("invalid property owner", validate(&fixture), WALLEYE_ADT_INVALID_STRUCTURE);

	initialize_valid(&fixture, 0);
	fixture.properties[0].reserved = 1u;
	failures += expect("reserved field", validate(&fixture), WALLEYE_ADT_INVALID_STRUCTURE);

	initialize_valid(&fixture, 1);
	fixture.nodes[1].path = span(gpu_path, 4u);
	fixture.nodes[1].node_type = WALLEYE_ADT_NODE_HARDWARE;
	failures += expect("active hardware node", validate(&fixture), WALLEYE_ADT_UNSUPPORTED_NODE);

	initialize_valid(&fixture, 0);
	failures += expect("normalized size mismatch",
		walleye_validate_normalized_adt(1u, fixture.nodes, 1u, fixture.properties, 1u,
		logical_size(&fixture) - 1u), WALLEYE_ADT_BOUNDS_VIOLATION);

	if (failures == 0) {
		(void)puts("walleye native ADT policy: all host cases passed");
	}
	return failures == 0 ? 0 : 1;
}
