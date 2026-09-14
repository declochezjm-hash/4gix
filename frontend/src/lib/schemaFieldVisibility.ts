import type { SchemaProperty } from "./api";

export type ShowWhen = Record<
	string,
	string | boolean | number | Array<string | boolean | number>
>;

function matchesExpected(actual: unknown, expected: unknown): boolean {
	if (Array.isArray(expected)) {
		return expected.some((item) => matchesExpected(actual, item));
	}
	if (typeof expected === "boolean") {
		return Boolean(actual) === expected;
	}
	return String(actual ?? "") === String(expected);
}

function resolveShowWhen(prop: SchemaProperty): ShowWhen | undefined {
	if (prop.showWhen) return prop.showWhen;
	const legacy = (prop as SchemaProperty & { "x-showWhen"?: ShowWhen })[
		"x-showWhen"
	];
	return legacy;
}

export function isSchemaFieldVisible(
	prop: SchemaProperty,
	params: Record<string, unknown>,
): boolean {
	const showWhen = resolveShowWhen(prop);
	if (!showWhen || Object.keys(showWhen).length === 0) {
		return true;
	}
	return Object.entries(showWhen).every(([key, expected]) =>
		matchesExpected(params[key], expected),
	);
}
