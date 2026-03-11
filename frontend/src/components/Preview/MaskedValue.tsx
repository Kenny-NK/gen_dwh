/**
 * Masked value display component (T069).
 */

import React from "react";

interface MaskedValueProps {
  value: string;
}

export function MaskedValue({ value }: MaskedValueProps) {
  return (
    <span
      className="inline-flex max-w-full items-center gap-1 rounded bg-amber-100 px-2 py-0.5 text-sm text-amber-800 dark:bg-amber-900/30 dark:text-amber-200"
      title={value}
    >
      <span className="text-xs">&#128274;</span>
      <span className="truncate whitespace-nowrap">{value}</span>
    </span>
  );
}
