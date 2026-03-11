import React from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { ApiErrorNotice } from "../common/ApiErrorNotice";
import { Button } from "../common/Button";
import { getAuthWorkspaces, switchWorkspace } from "../../services/authApi";

export function WorkspaceSelector() {
  const { data, isLoading } = useQuery({
    queryKey: ["auth-workspaces-selector"],
    queryFn: getAuthWorkspaces,
  });

  const switchMutation = useMutation({
    mutationFn: (workspaceId: string) => switchWorkspace(workspaceId),
    onSuccess: () => {
      window.location.assign("/");
    },
  });

  const workspaces = data?.items ?? [];

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-3xl rounded-[2rem] border border-slate-200 bg-white/95 p-8 shadow-panel backdrop-blur dark:border-slate-800 dark:bg-slate-900/95">
        <div className="max-w-2xl">
          <div className="text-xs font-semibold uppercase tracking-[0.28em] text-cyan-600 dark:text-cyan-300">
            GenDWH
          </div>
          <h1 className="mt-4 text-3xl font-semibold text-slate-900 dark:text-slate-100">
            Выберите tenant для работы
          </h1>
          <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-400">
            К вашей учетной записи привязано несколько tenant/workspace. Перед продолжением выберите,
            в каком tenant вы хотите работать сейчас.
          </p>
        </div>

        <div className="mt-8">
          {isLoading ? (
            <div className="rounded-2xl border border-dashed border-slate-300 px-4 py-10 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
              Загружаем доступные tenant-ы...
            </div>
          ) : workspaces.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-300 px-4 py-10 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
              Для учетной записи не найдено доступных tenant/workspace.
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {workspaces.map((workspace) => (
                <button
                  key={workspace.id}
                  type="button"
                  onClick={() => switchMutation.mutate(workspace.id)}
                  className="rounded-2xl border border-slate-200 bg-slate-50 px-5 py-5 text-left transition hover:border-cyan-400 hover:bg-cyan-50 dark:border-slate-800 dark:bg-slate-950/70 dark:hover:border-cyan-500 dark:hover:bg-slate-900"
                  disabled={switchMutation.isPending}
                >
                  <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                    {workspace.slug}
                  </div>
                  <div className="mt-3 text-xl font-semibold text-slate-900 dark:text-slate-100">
                    {workspace.name}
                  </div>
                  <div className="mt-2 text-sm text-slate-600 dark:text-slate-400">
                    Роль: {workspace.role}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {switchMutation.isError && (
          <ApiErrorNotice
            error={switchMutation.error}
            fallback="Не удалось переключить tenant"
            className="mt-6"
          />
        )}

        <div className="mt-8 flex justify-end">
          <Button variant="secondary" onClick={() => window.location.reload()}>
            Обновить список
          </Button>
        </div>
      </div>
    </div>
  );
}
