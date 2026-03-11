import React from "react";

import { extractApiErrorMessage } from "../../services/api";

interface ApiErrorNoticeProps {
  error: unknown;
  fallback: string;
  className?: string;
}

export function ApiErrorNotice({ error, fallback, className = "" }: ApiErrorNoticeProps) {
  const classes = [
    "rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700",
    "dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-200",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return <div className={classes}>{extractApiErrorMessage(error, fallback)}</div>;
}
