/**
 * Loading states and skeletons (T117).
 */

import React from "react";

export function Spinner({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const sizeClasses = { sm: "h-4 w-4", md: "h-8 w-8", lg: "h-12 w-12" };
  return (
    <div
      className={`animate-spin rounded-full border-2 border-slate-300 border-t-cyan-600 dark:border-slate-700 dark:border-t-cyan-400 ${sizeClasses[size]}`}
    />
  );
}

export function TableSkeleton({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="animate-pulse">
      <div className="mb-2 flex gap-4 border-b pb-2">
        {Array.from({ length: cols }).map((_, i) => (
          <div key={i} className="h-4 flex-1 rounded bg-slate-200 dark:bg-slate-800" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="mb-2 flex gap-4 py-2">
          {Array.from({ length: cols }).map((_, j) => (
            <div key={j} className="h-4 flex-1 rounded bg-slate-100 dark:bg-slate-900" />
          ))}
        </div>
      ))}
    </div>
  );
}

export function CardSkeleton() {
  return (
    <div className="animate-pulse rounded border border-slate-200 p-4 dark:border-slate-800">
      <div className="mb-2 h-4 w-24 rounded bg-slate-200 dark:bg-slate-800" />
      <div className="h-8 w-16 rounded bg-slate-100 dark:bg-slate-900" />
    </div>
  );
}

export function PageLoader() {
  return (
    <div className="flex h-64 items-center justify-center">
      <Spinner size="lg" />
    </div>
  );
}
