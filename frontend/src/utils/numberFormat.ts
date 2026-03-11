export type NumberLike = number | string | null | undefined;

export function toFiniteNumber(value: NumberLike): number | null {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }

  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return null;
    const normalized = trimmed.replace(/\s+/g, "").replace(",", ".");
    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : null;
  }

  return null;
}

export function formatNumberRu(value: NumberLike): string {
  const numberValue = toFiniteNumber(value);
  if (numberValue === null) return "0";

  const isInteger = Number.isInteger(numberValue);
  return new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: isInteger ? 0 : 2,
  }).format(numberValue);
}

export function formatCompactNumberRu(value: NumberLike): string {
  const numberValue = toFiniteNumber(value);
  if (numberValue === null) return "0";

  const absValue = Math.abs(numberValue);
  const sign = numberValue < 0 ? "-" : "";
  const units = [
    { value: 1_000_000_000_000, suffix: "трлн." },
    { value: 1_000_000_000, suffix: "млрд." },
    { value: 1_000_000, suffix: "млн." },
    { value: 1_000, suffix: "тыс." },
  ];

  for (const unit of units) {
    if (absValue >= unit.value) {
      const reduced = Math.floor(absValue / unit.value);
      return `${sign}${formatNumberRu(reduced)} ${unit.suffix}`;
    }
  }

  return formatNumberRu(numberValue);
}
