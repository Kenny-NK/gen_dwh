/**
 * Common Button component (T029).
 */

import React from "react";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
}

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  children,
  disabled,
  className = "",
  ...props
}: ButtonProps) {
  const baseStyles =
    "inline-flex items-center justify-center rounded-lg font-semibold tracking-wide transition focus:outline-none focus:ring-2 focus:ring-cyan-500/70 disabled:cursor-not-allowed";
  const variantStyles = {
    primary:
      "bg-cyan-600 text-white hover:bg-cyan-500 disabled:bg-cyan-300 dark:bg-cyan-500 dark:hover:bg-cyan-400 dark:disabled:bg-cyan-700",
    secondary:
      "bg-slate-200 text-slate-800 hover:bg-slate-300 disabled:bg-slate-100 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700 dark:disabled:bg-slate-900",
    danger:
      "bg-rose-600 text-white hover:bg-rose-500 disabled:bg-rose-300 dark:bg-rose-500 dark:hover:bg-rose-400 dark:disabled:bg-rose-700",
  };
  const sizeStyles = {
    sm: "px-3 py-1.5 text-sm",
    md: "px-4 py-2 text-sm",
    lg: "px-6 py-3 text-base",
  };

  return (
    <button
      className={`${baseStyles} ${variantStyles[variant]} ${sizeStyles[size]} ${className}`.trim()}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <span className="mr-2 animate-spin">⟳</span>}
      {children}
    </button>
  );
}
