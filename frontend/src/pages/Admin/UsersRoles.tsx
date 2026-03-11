import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Button } from "../../components/common/Button";
import { Input } from "../../components/common/Input";
import { Modal } from "../../components/common/Modal";
import { Table } from "../../components/common/Table";
import { useToast } from "../../components/common/Toast";
import { useErrorToast } from "../../hooks/useErrorToast";
import {
  createAdminTenant,
  createAdminUser,
  deleteAdminMembership,
  deleteAdminTenant,
  deleteAdminUser,
  getAdminTenants,
  getAdminUsers,
  type AdminTenant,
  type AdminUser,
  updateAdminTenant,
  updateAdminUser,
  upsertAdminMembership,
} from "../../services/adminApi";

type TenantFormState = {
  name: string;
  subdomain: string;
  schema_name: string;
  keycloak_realm: string;
  is_active: boolean;
};

type UserFormState = {
  keycloak_id: string;
  email: string;
  is_active: boolean;
};

const emptyTenantForm: TenantFormState = {
  name: "",
  subdomain: "",
  schema_name: "",
  keycloak_realm: "",
  is_active: true,
};

const emptyUserForm: UserFormState = {
  keycloak_id: "",
  email: "",
  is_active: true,
};

function MembershipPill({
  label,
  tone,
}: {
  label: string;
  tone: "active" | "muted";
}) {
  return (
    <span
      className={[
        "inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold",
        tone === "active"
          ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200"
          : "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
      ].join(" ")}
    >
      {label}
    </span>
  );
}

export default function UsersRoles() {
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  const { showErrorToast } = useErrorToast();
  const [tenantForm, setTenantForm] = React.useState<TenantFormState>(emptyTenantForm);
  const [userForm, setUserForm] = React.useState<UserFormState>(emptyUserForm);
  const [tenantSearch, setTenantSearch] = React.useState("");
  const [userSearch, setUserSearch] = React.useState("");
  const [userPage, setUserPage] = React.useState(1);
  const [editingTenant, setEditingTenant] = React.useState<AdminTenant | null>(null);
  const [editingUser, setEditingUser] = React.useState<AdminUser | null>(null);
  const [membershipUser, setMembershipUser] = React.useState<AdminUser | null>(null);
  const [membershipDraft, setMembershipDraft] = React.useState({
    tenantId: "",
    role: "user" as "owner" | "user" | "viewer",
  });
  const pageSize = 20;

  const { data: tenants = [], isLoading: tenantsLoading } = useQuery({
    queryKey: ["admin-tenants"],
    queryFn: getAdminTenants,
  });

  const { data: usersResponse, isLoading: usersLoading } = useQuery({
    queryKey: ["admin-users", userSearch, userPage],
    queryFn: () =>
      getAdminUsers({
        search: userSearch || undefined,
        limit: pageSize,
        offset: (userPage - 1) * pageSize,
      }),
  });

  const users = React.useMemo(() => usersResponse?.items ?? [], [usersResponse]);
  const totalUsers = usersResponse?.total ?? 0;
  const availableRoles = usersResponse?.available_roles ?? ["owner", "user", "viewer"];
  const activeTenants = tenants.filter((tenant) => tenant.is_active).length;
  const activeUsers = users.filter((user) => user.is_active).length;
  const membershipsTotal = users.reduce((acc, user) => acc + user.memberships.length, 0);
  const totalUserPages = Math.max(1, Math.ceil(totalUsers / pageSize));

  React.useEffect(() => {
    if (!membershipUser) {
      return;
    }
    const nextUser = users.find((item) => item.id === membershipUser.id);
    if (nextUser) {
      setMembershipUser(nextUser);
    }
  }, [membershipUser, users]);

  const invalidateAdminQueries = React.useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["admin-tenants"] });
    queryClient.invalidateQueries({ queryKey: ["admin-users"] });
  }, [queryClient]);

  const createTenantMutation = useMutation({
    mutationFn: () =>
      createAdminTenant({
        ...tenantForm,
        schema_name: tenantForm.schema_name || undefined,
        keycloak_realm: tenantForm.keycloak_realm || undefined,
      }),
    onSuccess: () => {
      addToast("success", "Tenant создан");
      setTenantForm(emptyTenantForm);
      invalidateAdminQueries();
    },
    onError: (error) => {
      showErrorToast(error, "Не удалось создать tenant");
    },
  });

  const updateTenantMutation = useMutation({
    mutationFn: (tenant: AdminTenant) =>
      updateAdminTenant(tenant.id, {
        name: tenant.name,
        subdomain: tenant.subdomain,
        keycloak_realm: tenant.keycloak_realm ?? "",
        is_active: tenant.is_active,
      }),
    onSuccess: () => {
      addToast("success", "Tenant обновлен");
      setEditingTenant(null);
      invalidateAdminQueries();
    },
    onError: (error) => {
      showErrorToast(error, "Не удалось обновить tenant");
    },
  });

  const deleteTenantMutation = useMutation({
    mutationFn: (tenantId: string) => deleteAdminTenant(tenantId),
    onSuccess: () => {
      addToast("success", "Tenant удален");
      invalidateAdminQueries();
    },
    onError: (error) => {
      showErrorToast(error, "Не удалось удалить tenant");
    },
  });

  const createUserMutation = useMutation({
    mutationFn: () => createAdminUser(userForm),
    onSuccess: () => {
      addToast("success", "Пользователь создан");
      setUserForm(emptyUserForm);
      invalidateAdminQueries();
    },
    onError: (error) => {
      showErrorToast(error, "Не удалось создать пользователя");
    },
  });

  const updateUserMutation = useMutation({
    mutationFn: (user: AdminUser) =>
      updateAdminUser(user.id, {
        email: user.email,
        keycloak_id: user.keycloak_id,
        is_active: user.is_active,
      }),
    onSuccess: () => {
      addToast("success", "Пользователь обновлен");
      setEditingUser(null);
      invalidateAdminQueries();
    },
    onError: (error) => {
      showErrorToast(error, "Не удалось обновить пользователя");
    },
  });

  const deleteUserMutation = useMutation({
    mutationFn: (userId: string) => deleteAdminUser(userId),
    onSuccess: () => {
      addToast("success", "Пользователь деактивирован");
      invalidateAdminQueries();
    },
    onError: (error) => {
      showErrorToast(error, "Не удалось удалить пользователя");
    },
  });

  const upsertMembershipMutation = useMutation({
    mutationFn: () => {
      if (!membershipUser) {
        throw new Error("Membership user is missing");
      }
      return upsertAdminMembership({
        userId: membershipUser.id,
        tenantId: membershipDraft.tenantId,
        role: membershipDraft.role,
      });
    },
    onSuccess: () => {
      addToast("success", "Роль назначена");
      setMembershipDraft((current) => ({ ...current, tenantId: "" }));
      invalidateAdminQueries();
    },
    onError: (error) => {
      showErrorToast(error, "Не удалось назначить роль");
    },
  });

  const deleteMembershipMutation = useMutation({
    mutationFn: (payload: { userId: string; membershipId: string }) => deleteAdminMembership(payload),
    onSuccess: () => {
      addToast("success", "Роль удалена");
      invalidateAdminQueries();
    },
    onError: (error) => {
      showErrorToast(error, "Не удалось удалить роль");
    },
  });

  const filteredTenants = React.useMemo(() => {
    const normalized = tenantSearch.trim().toLowerCase();
    if (!normalized) {
      return tenants;
    }
    return tenants.filter((tenant) =>
      [tenant.name, tenant.subdomain, tenant.schema_name, tenant.keycloak_realm ?? ""]
        .join(" ")
        .toLowerCase()
        .includes(normalized)
    );
  }, [tenantSearch, tenants]);

  const tenantColumns = [
    {
      key: "name",
      header: "Tenant / проект",
      render: (tenant: AdminTenant) => (
        <div>
          <div>{tenant.name}</div>
          <div className="text-xs font-normal text-slate-500 dark:text-slate-400">
            {tenant.subdomain}
          </div>
        </div>
      ),
    },
    { key: "schema_name", header: "Schema" },
    {
      key: "keycloak_realm",
      header: "Realm",
      render: (tenant: AdminTenant) => tenant.keycloak_realm || "—",
    },
    {
      key: "status",
      header: "Статус",
      render: (tenant: AdminTenant) => (
        <MembershipPill label={tenant.is_active ? "Активен" : "Выключен"} tone={tenant.is_active ? "active" : "muted"} />
      ),
    },
    {
      key: "actions",
      header: "Действия",
      render: (tenant: AdminTenant) => (
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="secondary"
            onClick={(event) => {
              event.stopPropagation();
              setEditingTenant(tenant);
            }}
          >
            Изменить
          </Button>
          <Button
            size="sm"
            variant="danger"
            onClick={(event) => {
              event.stopPropagation();
              if (window.confirm(`Удалить tenant "${tenant.name}"?`)) {
                deleteTenantMutation.mutate(tenant.id);
              }
            }}
          >
            Удалить
          </Button>
        </div>
      ),
    },
  ];

  const userColumns = [
    {
      key: "email",
      header: "Пользователь",
      render: (user: AdminUser) => (
        <div>
          <div>{user.email}</div>
          <div className="text-xs font-normal text-slate-500 dark:text-slate-400">
            {user.keycloak_id}
          </div>
        </div>
      ),
    },
    {
      key: "memberships",
      header: "Роли и доступы",
      render: (user: AdminUser) => (
        <div className="flex flex-wrap gap-1.5">
          {user.memberships.length === 0 && <MembershipPill label="Нет доступов" tone="muted" />}
          {user.memberships.map((membership) => (
            <MembershipPill
              key={membership.id}
              label={`${membership.tenant_subdomain}: ${membership.role}`}
              tone={membership.deleted_at || membership.revoked_at ? "muted" : "active"}
            />
          ))}
        </div>
      ),
    },
    {
      key: "status",
      header: "Статус",
      render: (user: AdminUser) => (
        <MembershipPill label={user.is_active ? "Активен" : "Отключен"} tone={user.is_active ? "active" : "muted"} />
      ),
    },
    {
      key: "actions",
      header: "Действия",
      render: (user: AdminUser) => (
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="secondary"
            onClick={(event) => {
              event.stopPropagation();
              setMembershipUser(user);
              setMembershipDraft((current) => ({
                ...current,
                tenantId: tenants[0]?.id ?? "",
              }));
            }}
          >
            Роли
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={(event) => {
              event.stopPropagation();
              setEditingUser(user);
            }}
          >
            Изменить
          </Button>
          <Button
            size="sm"
            variant="danger"
            onClick={(event) => {
              event.stopPropagation();
              if (window.confirm(`Отключить пользователя "${user.email}"?`)) {
                deleteUserMutation.mutate(user.id);
              }
            }}
          >
            Удалить
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Пользователи и роли</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600 dark:text-slate-400">
          Единый административный раздел для управления tenant/workspace структурой проекта, пользователями и их ролями.
        </p>
      </div>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="app-card p-4">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
            Тенанты
          </div>
          <div className="mt-3 text-3xl font-semibold text-slate-900 dark:text-slate-100">{tenants.length}</div>
          <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">Активных: {activeTenants}</div>
        </div>
        <div className="app-card p-4">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
            Пользователи
          </div>
          <div className="mt-3 text-3xl font-semibold text-slate-900 dark:text-slate-100">{totalUsers}</div>
          <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">Активных на странице: {activeUsers}</div>
        </div>
        <div className="app-card p-4">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
            Назначения ролей
          </div>
          <div className="mt-3 text-3xl font-semibold text-slate-900 dark:text-slate-100">{membershipsTotal}</div>
          <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">Для текущей страницы пользователей</div>
        </div>
        <div className="app-card p-4">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
            Синхронизация
          </div>
          <div className="mt-3 text-sm text-slate-600 dark:text-slate-300">
            Обнови каталоги tenant-ов и пользователей вручную после изменений.
          </div>
          <Button
            className="mt-3 w-full"
            variant="secondary"
            onClick={invalidateAdminQueries}
          >
            Обновить данные
          </Button>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_1fr]">
        <section className="app-card p-5">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Тенанты и проекты</h2>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                Создание и управление tenant/workspace схемами проекта.
              </p>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <Input
              label="Название"
              value={tenantForm.name}
              onChange={(event) => setTenantForm((current) => ({ ...current, name: event.target.value }))}
              placeholder="Acme Corp"
            />
            <Input
              label="Subdomain"
              value={tenantForm.subdomain}
              onChange={(event) => setTenantForm((current) => ({ ...current, subdomain: event.target.value }))}
              placeholder="acme"
            />
            <Input
              label="Schema"
              value={tenantForm.schema_name}
              onChange={(event) => setTenantForm((current) => ({ ...current, schema_name: event.target.value }))}
              placeholder="tenant_acme"
            />
            <Input
              label="Keycloak realm"
              value={tenantForm.keycloak_realm}
              onChange={(event) => setTenantForm((current) => ({ ...current, keycloak_realm: event.target.value }))}
              placeholder="gendwh"
            />
          </div>
          <label className="mt-3 flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
            <input
              type="checkbox"
              checked={tenantForm.is_active}
              onChange={(event) => setTenantForm((current) => ({ ...current, is_active: event.target.checked }))}
              className="h-4 w-4 rounded border-slate-300"
            />
            Активировать tenant сразу после создания
          </label>
          <div className="mt-4 flex items-center gap-3">
            <Button
              onClick={() => createTenantMutation.mutate()}
              loading={createTenantMutation.isPending}
              disabled={!tenantForm.name.trim() || !tenantForm.subdomain.trim()}
            >
              Создать tenant
            </Button>
            <Input
              value={tenantSearch}
              onChange={(event) => setTenantSearch(event.target.value)}
              placeholder="Поиск tenant"
            />
          </div>

          <div className="mt-4">
            {tenantsLoading ? (
              <div>Загрузка...</div>
            ) : (
              <Table
                columns={tenantColumns}
                data={filteredTenants}
                emptyMessage="Tenant-ов пока нет"
              />
            )}
          </div>
        </section>

        <section className="app-card p-5">
          <div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Пользователи</h2>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              Локальный каталог пользователей и их ролевые назначения по tenant-ам.
            </p>
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <Input
              label="Email"
              value={userForm.email}
              onChange={(event) => setUserForm((current) => ({ ...current, email: event.target.value }))}
              placeholder="user@example.com"
            />
            <Input
              label="Keycloak ID"
              value={userForm.keycloak_id}
              onChange={(event) => setUserForm((current) => ({ ...current, keycloak_id: event.target.value }))}
              placeholder="realm-user-id"
            />
          </div>
          <label className="mt-3 flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
            <input
              type="checkbox"
              checked={userForm.is_active}
              onChange={(event) => setUserForm((current) => ({ ...current, is_active: event.target.checked }))}
              className="h-4 w-4 rounded border-slate-300"
            />
            Пользователь активен
          </label>
          <div className="mt-4 flex items-center gap-3">
            <Button
              onClick={() => createUserMutation.mutate()}
              loading={createUserMutation.isPending}
              disabled={!userForm.email.trim() || !userForm.keycloak_id.trim()}
            >
              Создать пользователя
            </Button>
            <Input
              value={userSearch}
              onChange={(event) => {
                setUserSearch(event.target.value);
                setUserPage(1);
              }}
              placeholder="Поиск пользователя"
            />
          </div>

          <div className="mt-4">
            {usersLoading ? (
              <div>Загрузка...</div>
            ) : (
              <>
                <Table columns={userColumns} data={users} emptyMessage="Пользователи не найдены" />
                <div className="mt-4 flex items-center justify-between text-sm text-slate-500 dark:text-slate-400">
                  <span>
                    Всего пользователей: {totalUsers} • Страница {userPage} из {totalUserPages}
                  </span>
                  <div className="flex gap-2">
                    <Button
                      variant="secondary"
                      onClick={() => setUserPage((current) => Math.max(1, current - 1))}
                      disabled={userPage === 1}
                    >
                      Назад
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => setUserPage((current) => current + 1)}
                      disabled={userPage >= totalUserPages}
                    >
                      Далее
                    </Button>
                  </div>
                </div>
              </>
            )}
          </div>
        </section>
      </div>

      <Modal
        isOpen={editingTenant !== null}
        onClose={() => setEditingTenant(null)}
        title="Редактирование tenant"
      >
        {editingTenant && (
          <div className="space-y-3">
            <Input
              label="Название"
              value={editingTenant.name}
              onChange={(event) =>
                setEditingTenant((current) => (current ? { ...current, name: event.target.value } : current))
              }
            />
            <Input
              label="Subdomain"
              value={editingTenant.subdomain}
              onChange={(event) =>
                setEditingTenant((current) => (current ? { ...current, subdomain: event.target.value } : current))
              }
            />
            <Input
              label="Keycloak realm"
              value={editingTenant.keycloak_realm ?? ""}
              onChange={(event) =>
                setEditingTenant((current) =>
                  current ? { ...current, keycloak_realm: event.target.value || null } : current
                )
              }
            />
            <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
              <input
                type="checkbox"
                checked={editingTenant.is_active}
                onChange={(event) =>
                  setEditingTenant((current) => (current ? { ...current, is_active: event.target.checked } : current))
                }
                className="h-4 w-4 rounded border-slate-300"
              />
              Tenant активен
            </label>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setEditingTenant(null)}>
                Отмена
              </Button>
              <Button
                onClick={() => editingTenant && updateTenantMutation.mutate(editingTenant)}
                loading={updateTenantMutation.isPending}
              >
                Сохранить
              </Button>
            </div>
          </div>
        )}
      </Modal>

      <Modal
        isOpen={editingUser !== null}
        onClose={() => setEditingUser(null)}
        title="Редактирование пользователя"
      >
        {editingUser && (
          <div className="space-y-3">
            <Input
              label="Email"
              value={editingUser.email}
              onChange={(event) =>
                setEditingUser((current) => (current ? { ...current, email: event.target.value } : current))
              }
            />
            <Input
              label="Keycloak ID"
              value={editingUser.keycloak_id}
              onChange={(event) =>
                setEditingUser((current) =>
                  current ? { ...current, keycloak_id: event.target.value } : current
                )
              }
            />
            <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
              <input
                type="checkbox"
                checked={editingUser.is_active}
                onChange={(event) =>
                  setEditingUser((current) => (current ? { ...current, is_active: event.target.checked } : current))
                }
                className="h-4 w-4 rounded border-slate-300"
              />
              Пользователь активен
            </label>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setEditingUser(null)}>
                Отмена
              </Button>
              <Button
                onClick={() => editingUser && updateUserMutation.mutate(editingUser)}
                loading={updateUserMutation.isPending}
              >
                Сохранить
              </Button>
            </div>
          </div>
        )}
      </Modal>

      <Modal
        isOpen={membershipUser !== null}
        onClose={() => setMembershipUser(null)}
        title="Управление ролями"
      >
        {membershipUser && (
          <div className="space-y-4">
            <div>
              <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{membershipUser.email}</div>
              <div className="text-xs text-slate-500 dark:text-slate-400">{membershipUser.keycloak_id}</div>
            </div>

            <div className="grid gap-3 md:grid-cols-[1fr_160px_auto]">
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Tenant</label>
                <select
                  value={membershipDraft.tenantId}
                  onChange={(event) =>
                    setMembershipDraft((current) => ({ ...current, tenantId: event.target.value }))
                  }
                  className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:ring-2 focus:ring-cyan-500/70 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                >
                  <option value="">Выберите tenant</option>
                  {tenants.map((tenant) => (
                    <option key={tenant.id} value={tenant.id}>
                      {tenant.name} ({tenant.subdomain})
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Роль</label>
                <select
                  value={membershipDraft.role}
                  onChange={(event) =>
                    setMembershipDraft((current) => ({
                      ...current,
                      role: event.target.value as "owner" | "user" | "viewer",
                    }))
                  }
                  className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:ring-2 focus:ring-cyan-500/70 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                >
                  {availableRoles.map((role) => (
                    <option key={role} value={role}>
                      {role}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex items-end">
                <Button
                  onClick={() => upsertMembershipMutation.mutate()}
                  loading={upsertMembershipMutation.isPending}
                  disabled={!membershipDraft.tenantId}
                >
                  Назначить
                </Button>
              </div>
            </div>

            <div className="space-y-2">
              {membershipUser.memberships.length === 0 && (
                <div className="rounded-lg border border-dashed border-slate-300 px-3 py-4 text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
                  У пользователя пока нет ролей.
                </div>
              )}
              {membershipUser.memberships.length > 0 && (
                <div className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500 dark:bg-slate-800/70 dark:text-slate-400">
                  Активные и исторические назначения ролей по tenant-ам. Удаление роли снимает доступ пользователя к выбранному tenant.
                </div>
              )}
              {membershipUser.memberships.map((membership) => (
                <div
                  key={membership.id}
                  className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-3 dark:border-slate-700"
                >
                  <div>
                    <div className="text-sm font-medium text-slate-900 dark:text-slate-100">
                      {membership.tenant_name}
                    </div>
                    <div className="text-xs text-slate-500 dark:text-slate-400">
                      {membership.tenant_subdomain} • {membership.role}
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() =>
                      deleteMembershipMutation.mutate({
                        userId: membershipUser.id,
                        membershipId: membership.id,
                      })
                    }
                    loading={deleteMembershipMutation.isPending}
                  >
                    Удалить
                  </Button>
                </div>
              ))}
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
