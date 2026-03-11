export function stringifyPreviewValue(value: unknown): string {
  if (typeof value !== "object" || value === null) {
    return String(value ?? "");
  }
  try {
    return JSON.stringify(value);
  } catch {
    return "[Object]";
  }
}

export function isMaskedPreviewValue(value: unknown): value is string {
  return typeof value === "string" && value.includes("***");
}
