export function formatDateTime(value: string | Date | null | undefined, fallback = "—"): string {
  if (!value) {
    return fallback;
  }

  const parsed = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return fallback;
  }

  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(parsed);
}
