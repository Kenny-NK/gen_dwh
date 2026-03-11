export type RunStatusUiConfig = {
  label: string;
  badgeClassName: string;
  progressToneClassName: string;
  fallbackActivityLabel: string;
};

export const runStatusUiConfig: Record<string, RunStatusUiConfig> = {
  pending: {
    label: "Ожидание",
    badgeClassName: "bg-slate-200 text-slate-800 dark:bg-slate-700 dark:text-slate-200",
    progressToneClassName: "bg-cyan-500",
    fallbackActivityLabel: "Ожидание очереди",
  },
  running: {
    label: "Выполняется",
    badgeClassName: "bg-cyan-100 text-cyan-800 dark:bg-cyan-900/30 dark:text-cyan-200",
    progressToneClassName: "bg-cyan-500",
    fallbackActivityLabel: "Идет обработка данных",
  },
  success: {
    label: "Успешно",
    badgeClassName: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-200",
    progressToneClassName: "bg-emerald-500",
    fallbackActivityLabel: "Завершено",
  },
  failed: {
    label: "Ошибка",
    badgeClassName: "bg-rose-100 text-rose-800 dark:bg-rose-900/30 dark:text-rose-200",
    progressToneClassName: "bg-rose-500",
    fallbackActivityLabel: "Завершено",
  },
  cancelled: {
    label: "Отменен",
    badgeClassName: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-200",
    progressToneClassName: "bg-amber-500",
    fallbackActivityLabel: "Завершено",
  },
};

export function getRunStatusUiConfig(status: string): RunStatusUiConfig {
  return runStatusUiConfig[status] ?? runStatusUiConfig.pending;
}
