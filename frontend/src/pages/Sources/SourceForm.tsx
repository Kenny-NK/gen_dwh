/**
 * Source form component - create/edit (T046, T048, T049).
 */

import React, { useState, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { extractApiErrorMessage } from "../../services/api";
import { Button } from "../../components/common/Button";
import { Input } from "../../components/common/Input";
import { ConnectionStatus } from "../../components/ConnectionStatus";
import { useToast } from "../../components/common/Toast";

interface SourceFormData {
  name: string;
  host: string;
  port: number;
  database: string;
  username: string;
  password: string;
  description: string;
}

interface SourceResponse {
  name: string;
  host: string;
  port: number;
  database: string;
  username: string;
  description?: string | null;
}

interface SourceTestResponse {
  success: boolean;
  message: string;
}

const defaultForm: SourceFormData = {
  name: "",
  host: "",
  port: 5432,
  database: "",
  username: "",
  password: "",
  description: "",
};

export default function SourceForm() {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isEditing = !!id;

  const [form, setForm] = useState<SourceFormData>(defaultForm);
  const [testResult, setTestResult] = useState<{
    success: boolean;
    message: string;
  } | null>(null);
  const { addToast } = useToast();

  const getErrorMessage = (error: unknown): string => {
    return extractApiErrorMessage(error, "Ошибка запроса. Проверьте параметры и попробуйте снова.");
  };

  const {
    data: source,
    isError: isSourceError,
    error: sourceError,
  } = useQuery<SourceResponse>({
    queryKey: ["source", id],
    queryFn: () => api.get(`/sources/${id}`).then((r) => r.data),
    enabled: isEditing,
    retry: false,
  });

  useEffect(() => {
    if (isSourceError) {
      addToast("error", getErrorMessage(sourceError));
    }
  }, [isSourceError, sourceError, addToast]);

  useEffect(() => {
    if (source) {
      setForm({
        name: source.name,
        host: source.host,
        port: source.port,
        database: source.database,
        username: source.username,
        password: "",
        description: source.description || "",
      });
    }
  }, [source]);

  const saveMutation = useMutation({
    mutationFn: (data: SourceFormData) =>
      isEditing
        ? api.patch(`/sources/${id}`, data)
        : api.post("/sources", data),
    onSuccess: () => {
      addToast("success", isEditing ? "Источник обновлен" : "Источник создан");
      queryClient.invalidateQueries({ queryKey: ["sources"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-sources"] });
      navigate("/sources");
    },
    onError: (error) => {
      addToast("error", getErrorMessage(error));
    },
  });

  const testMutation = useMutation({
    mutationFn: () => api.post(`/sources/${id}/test`).then((r) => r.data),
    onSuccess: (data: SourceTestResponse) => {
      setTestResult(data);
      addToast("info", data.success ? "Подключение успешно" : data.message);
    },
    onError: (error) => {
      addToast("error", getErrorMessage(error));
    },
  });

  const updateField = (field: keyof SourceFormData, value: string | number) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  return (
    <div className="mx-auto max-w-xl app-card p-6">
      <h1 className="mb-6 text-2xl font-bold text-slate-900 dark:text-slate-100">
        {isEditing ? "Редактирование источника" : "Новый источник"}
      </h1>

      <div className="space-y-4">
        <Input
          label="Название"
          id="name"
          value={form.name}
          onChange={(e) => updateField("name", e.target.value)}
          required
        />
        <Input
          label="Хост"
          id="host"
          value={form.host}
          onChange={(e) => updateField("host", e.target.value)}
          required
        />
        <Input
          label="Порт"
          id="port"
          type="number"
          value={form.port}
          onChange={(e) => {
            const parsed = Number.parseInt(e.target.value, 10);
            updateField("port", Number.isNaN(parsed) ? 5432 : parsed);
          }}
          required
        />
        <Input
          label="База данных"
          id="database"
          value={form.database}
          onChange={(e) => updateField("database", e.target.value)}
          required
        />
        <Input
          label="Пользователь"
          id="username"
          value={form.username}
          onChange={(e) => updateField("username", e.target.value)}
          required
        />
        <Input
          label="Пароль"
          id="password"
          type="password"
          value={form.password}
          onChange={(e) => updateField("password", e.target.value)}
          placeholder={isEditing ? "Оставьте пустым, чтобы не менять" : ""}
          required={!isEditing}
        />
        <Input
          label="Описание"
          id="description"
          value={form.description}
          onChange={(e) => updateField("description", e.target.value)}
        />

        {testResult && (
          <div
            className={`rounded-lg p-3 ${
              testResult.success
                ? "bg-emerald-50 dark:bg-emerald-900/20"
                : "bg-rose-50 dark:bg-rose-900/20"
            }`}
          >
            <ConnectionStatus status={testResult.success ? "valid" : "invalid"} />
            <span className="ml-2 text-sm text-slate-700 dark:text-slate-200">{testResult.message}</span>
          </div>
        )}

        <div className="flex gap-2 pt-4">
          <Button
            onClick={() => saveMutation.mutate(form)}
            loading={saveMutation.isPending}
          >
            {isEditing ? "Сохранить" : "Создать"}
          </Button>
          {isEditing && (
            <Button
              variant="secondary"
              onClick={() => testMutation.mutate()}
              loading={testMutation.isPending}
            >
              Проверить подключение
            </Button>
          )}
          <Button variant="secondary" onClick={() => navigate("/sources")}>
            Отмена
          </Button>
        </div>
      </div>
    </div>
  );
}
