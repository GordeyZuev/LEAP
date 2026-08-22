"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ShieldCheck,
  Loader2,
  X,
  Users,
  UserCheck,
  HardDrive,
  Film,
  Plus,
  Pencil,
  AlertTriangle,
} from "lucide-react";
import { apiClient } from "@/api/client";
import { cn, extractApiError, formatRelative, formatDateTime } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";
import { useDebounce } from "@/hooks/use-debounce";
import { Toast } from "@/components/ui/toast";
import { PageHeader } from "@/components/ui/page-header";
import { AdminAuditLog } from "@/components/admin/audit-log";
import { Toggle } from "@/components/ui/toggle";
import { SortableTh } from "@/components/ui/sortable-th";
import { TABLE_BODY, TABLE_CARD, TABLE_HEAD_CELL, TABLE_ROW } from "@/lib/table-classes";
import { ActionButton } from "@/components/ui/action-button";
import { Modal } from "@/components/ui/modal";
import { ModalSection } from "@/components/ui/section-card";
import { NativeSelect } from "@/components/ui/native-select";
import { Pagination } from "@/components/ui/pagination";
import { EmptyState } from "@/components/ui/empty-state";
import { SearchInput } from "@/components/filters/search-input";
import { FilterBar } from "@/components/filters/filter-bar";
import { SegmentedFilter } from "@/components/filters/segmented-filter";
import { DEBOUNCE_SEARCH } from "@/lib/constants";
import { FILTER_CONTROL, FILTER_LABEL } from "@/lib/filter-field-classes";
import {
  PERMISSION_FLAGS,
  type PermissionKey,
  type AdminUserProfile,
  type AdminPlan,
  type AdminPlanCreate,
  type AdminPlanUpdate,
  type UserQuotaDetails,
  fetchAdminUsers,
  fetchAdminUserStats,
  updateAdminUser,
  fetchAdminPlans,
  fetchUserSubscription,
  setUserSubscription,
  deleteUserSubscription,
  createAdminPlan,
  updateAdminPlan,
  type SubscriptionSetBody,
} from "@/api/admin";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface OverviewStats {
  total_users: number;
  active_users: number;
  total_recordings: number;
  total_storage_gb: number;
  total_plans: number;
  users_by_plan: Record<string, number>;
  exceeding_users_count: number;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZE = 50;

const ROLE_OPTIONS = [
  { value: "all", label: "All roles" },
  { value: "user", label: "Users" },
  { value: "admin", label: "Admins" },
];

const EXCEEDED_OPTIONS = [
  { value: "all", label: "All users" },
  { value: "exceeded", label: "Over quota" },
];

// Fields editable per-user as subscription overrides
const LIMIT_FIELDS = [
  { key: "custom_max_recordings_per_month", planKey: "included_recordings_per_month", label: "Recordings / month" },
  { key: "custom_max_storage_gb", planKey: "included_storage_gb", label: "Storage (GB)" },
  { key: "custom_max_concurrent_tasks", planKey: "max_concurrent_tasks", label: "Concurrent tasks" },
  { key: "custom_max_automation_jobs", planKey: "max_automation_jobs", label: "Automation jobs" },
  { key: "custom_min_automation_interval_hours", planKey: "min_automation_interval_hours", label: "Min interval (h)" },
  { key: "custom_max_templates", planKey: "max_templates", label: "Templates" },
  { key: "custom_max_credentials", planKey: "max_credentials", label: "Credentials" },
] as const;

type LimitKey = (typeof LIMIT_FIELDS)[number]["key"];

// Plan quota fields for create/edit modal
const PLAN_QUOTA_FIELDS = [
  { key: "included_recordings_per_month", label: "Recordings / month" },
  { key: "included_storage_gb", label: "Storage (GB)" },
  { key: "max_concurrent_tasks", label: "Concurrent tasks" },
  { key: "max_automation_jobs", label: "Automation jobs" },
  { key: "min_automation_interval_hours", label: "Min automation interval (h)" },
  { key: "max_transcriptions_per_month", label: "Transcriptions / month" },
  { key: "max_processing_per_month", label: "Processing / month" },
  { key: "max_templates", label: "Templates" },
  { key: "max_credentials", label: "Credentials" },
] as const;

type PlanQuotaKey = (typeof PLAN_QUOTA_FIELDS)[number]["key"];

// ---------------------------------------------------------------------------
// UI atoms — match settings/page.tsx exactly
// ---------------------------------------------------------------------------

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className={cn(FILTER_LABEL, "mb-1.5")}>{label}</label>
      {hint && <p className="text-xs text-muted-foreground mb-1.5">{hint}</p>}
      {children}
    </div>
  );
}


function StatRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-border py-2.5 last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-sm font-semibold tabular-nums text-foreground">{value}</span>
    </div>
  );
}

function RoleBadge({ role }: { role: string }) {
  return (
    <span
      className={cn(
        "rounded-full px-2.5 py-0.5 text-xs font-medium",
        role === "admin" ? "bg-primary/10 text-primary" : "bg-muted text-secondary-foreground",
      )}
    >
      {role}
    </span>
  );
}

function StatusBadge({ active }: { active: boolean }) {
  return (
    <span
      className={cn(
        "rounded-full px-2.5 py-0.5 text-xs font-medium",
        active ? "bg-green-50 text-green-600 dark:bg-green-500/10" : "bg-muted text-muted-foreground",
      )}
    >
      {active ? "Active" : "Inactive"}
    </span>
  );
}

function QuotaBadge({ exceeding }: { exceeding: boolean }) {
  return (
    <span
      className={cn(
        "rounded-full px-2.5 py-0.5 text-xs font-medium",
        exceeding
          ? "bg-amber-50 text-amber-600 dark:bg-amber-500/10"
          : "bg-green-50 text-green-600 dark:bg-green-500/10",
      )}
    >
      {exceeding ? "Over" : "OK"}
    </span>
  );
}

function fmtQuota(v: number | null | undefined): string {
  if (v === null || v === undefined) return "∞";
  return String(v);
}

function fmtUsage(used: number, limit: number | null): string {
  return `${used} / ${limit === null ? "∞" : limit}`;
}

// ---------------------------------------------------------------------------
// Overview stat card
// ---------------------------------------------------------------------------

function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
}) {
  return (
    <div className="bg-card rounded-2xl border border-border shadow-sm p-5 flex items-center gap-4">
      <div className="shrink-0 rounded-xl bg-primary/8 p-3 text-primary">
        <Icon size={18} />
      </div>
      <div className="min-w-0">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{label}</p>
        <p className="mt-0.5 text-2xl font-semibold tabular-nums text-foreground">{value}</p>
      </div>
    </div>
  );
}

// Pure-CSS stacked bar chart for plan distribution
function PlanDistributionChart({ data }: { data: Record<string, number> }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((s, [, v]) => s + v, 0);
  if (total === 0 || entries.length === 0) {
    return <p className="text-sm text-muted-foreground">No users with subscriptions yet.</p>;
  }

  const COLORS = ["bg-primary", "bg-blue-400", "bg-indigo-400", "bg-violet-400", "bg-cyan-400", "bg-teal-400"];

  return (
    <div className="space-y-3">
      <div className="flex h-3 w-full overflow-hidden rounded-full">
        {entries.map(([plan, count], i) => (
          <div
            key={plan}
            style={{ width: `${(count / total) * 100}%` }}
            className={cn(COLORS[i % COLORS.length])}
            title={`${plan}: ${count}`}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-1.5">
        {entries.map(([plan, count], i) => (
          <div key={plan} className="flex items-center gap-1.5">
            <span className={cn("inline-block h-2.5 w-2.5 shrink-0 rounded-sm", COLORS[i % COLORS.length])} />
            <span className="text-xs font-medium text-secondary-foreground">{plan}</span>
            <span className="text-xs text-muted-foreground">
              {count} ({Math.round((count / total) * 100)}%)
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page guard
// ---------------------------------------------------------------------------

export default function AdminPage() {
  const me = useQuery({
    queryKey: ["me"],
    queryFn: async () => (await apiClient.get("/users/me")).data as { role: string },
  });

  if (me.isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (me.data?.role !== "admin") {
    return (
      <EmptyState
        icon={ShieldCheck}
        title="Access denied"
        description="This area is restricted to administrators."
      />
    );
  }

  return <AdminDashboard />;
}

// ---------------------------------------------------------------------------
// Main dashboard
// ---------------------------------------------------------------------------

function AdminDashboard() {
  const qc = useQueryClient();
  const { toast, show, dismiss } = useToast();

  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("all");
  const [exceededFilter, setExceededFilter] = useState("all");
  const [editingUser, setEditingUser] = useState<AdminUserProfile | null>(null);
  const [editingPlan, setEditingPlan] = useState<AdminPlan | null | "new">(null);

  const debouncedSearch = useDebounce(search, DEBOUNCE_SEARCH);

  const overviewQuery = useQuery<OverviewStats>({
    queryKey: ["admin-overview"],
    queryFn: async () => (await apiClient.get("/admin/stats/overview")).data,
    staleTime: 60_000,
  });

  const plansQuery = useQuery<AdminPlan[]>({
    queryKey: ["admin-plans"],
    queryFn: fetchAdminPlans,
  });

  const exceededOnly = exceededFilter === "exceeded";

  const usersQuery = useQuery({
    queryKey: ["admin-users", page, debouncedSearch, roleFilter, exceededOnly],
    queryFn: () =>
      fetchAdminUsers({
        page,
        page_size: PAGE_SIZE,
        search: debouncedSearch || undefined,
        role: roleFilter === "all" ? undefined : roleFilter,
        exceeded_only: exceededOnly || undefined,
      }),
  });

  const userStatsQuery = useQuery({
    queryKey: ["admin-user-stats", page, exceededOnly],
    queryFn: () => fetchAdminUserStats({ page, page_size: PAGE_SIZE, exceeded_only: exceededOnly || undefined }),
    staleTime: 60_000,
  });

  const ov = overviewQuery.data;
  const plans = plansQuery.data ?? [];
  const users = usersQuery.data?.users ?? [];
  const total = usersQuery.data?.total_count ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  // Merge usage stats by user_id
  const statsById = useMemo(() => {
    const map = new Map<string, UserQuotaDetails>();
    for (const s of userStatsQuery.data?.users ?? []) map.set(s.user_id, s);
    return map;
  }, [userStatsQuery.data]);

  function handlePlanSaved() {
    void qc.invalidateQueries({ queryKey: ["admin-plans"] });
    void qc.invalidateQueries({ queryKey: ["admin-overview"] });
    setEditingPlan(null);
    show("success", "Plan saved");
  }

  function handleUserSaved() {
    void qc.invalidateQueries({ queryKey: ["admin-users"] });
    void qc.invalidateQueries({ queryKey: ["admin-user-stats"] });
    void qc.invalidateQueries({ queryKey: ["admin-subscription"] });
    void qc.invalidateQueries({ queryKey: ["admin-overview"] });
    setEditingUser(null);
    show("success", "User updated");
  }

  return (
    <div className="w-full min-w-0 p-6 sm:p-8">
      <PageHeader title="Admin" />

      <div className="space-y-6">
        {/* ── Overview ──────────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
          <StatCard icon={Users} label="Total users" value={ov?.total_users ?? "—"} />
          <StatCard icon={UserCheck} label="Active users" value={ov?.active_users ?? "—"} />
          <StatCard icon={Film} label="Recordings" value={ov?.total_recordings ?? "—"} />
          <StatCard
            icon={HardDrive}
            label="Storage"
            value={ov ? `${ov.total_storage_gb.toFixed(1)} GB` : "—"}
          />
          <StatCard
            icon={AlertTriangle}
            label="Over quota"
            value={ov?.exceeding_users_count ?? "—"}
          />
        </div>

        {/* Plan distribution — only shown when there are subscribers */}
        {ov && Object.keys(ov.users_by_plan).length > 0 && (
          <div>
            <h2 className="mb-3 text-sm font-semibold text-foreground">Users by plan</h2>
            <div className="rounded-2xl border border-border bg-card p-5 shadow-sm">
              <PlanDistributionChart data={ov.users_by_plan} />
            </div>
          </div>
        )}

        {/* ── Plans ─────────────────────────────────────────────────────── */}
        <div>
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 className="text-sm font-semibold text-foreground">Subscription plans</h2>
            <ActionButton
              size="sm"
              onClick={() => setEditingPlan("new")}
              icon={<Plus size={13} />}
            >
              New plan
            </ActionButton>
          </div>

          <div className={TABLE_CARD}>
          {plansQuery.isLoading ? (
            <div className="flex h-24 items-center justify-center">
              <Loader2 size={18} className="animate-spin text-muted-foreground" />
            </div>
          ) : plans.length === 0 ? (
            <div className="px-6 py-8 text-center">
              <p className="text-sm text-muted-foreground">No plans yet.</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Create a plan first, then assign it to users.
              </p>
            </div>
          ) : (
              <table className="w-full min-w-[700px]">
                <thead>
                  <tr className="border-b border-border">
                    <SortableTh label="Plan" />
                    <SortableTh label="Recordings / mo" title="Recordings per month" />
                    <SortableTh label="Storage" />
                    <SortableTh label="Tasks" />
                    <SortableTh label="Templates" />
                    <SortableTh label="Credentials" />
                    <SortableTh label="Users" />
                    <th
                      scope="col"
                      className={cn(
                        TABLE_HEAD_CELL,
                        "sticky top-0 z-10 bg-muted text-right last:rounded-tr-2xl",
                      )}
                    >
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody className={TABLE_BODY}>
                  {plans.map((plan) => (
                    <tr
                      key={plan.id}
                      onClick={() => setEditingPlan(plan)}
                      className={cn(TABLE_ROW, "cursor-pointer")}
                    >
                      <td className="px-6 py-3.5">
                        <p className="text-sm font-medium text-foreground">{plan.display_name}</p>
                        {plan.name !== plan.display_name && (
                          <p className="text-xs text-muted-foreground">{plan.name}</p>
                        )}
                      </td>
                      <td className="px-6 py-3.5 text-sm text-secondary-foreground tabular-nums">
                        {fmtQuota(plan.included_recordings_per_month)}
                      </td>
                      <td className="px-6 py-3.5 text-sm text-secondary-foreground tabular-nums">
                        {fmtQuota(plan.included_storage_gb)} GB
                      </td>
                      <td className="px-6 py-3.5 text-sm text-secondary-foreground tabular-nums">
                        {fmtQuota(plan.max_concurrent_tasks)}
                      </td>
                      <td className="px-6 py-3.5 text-sm text-secondary-foreground tabular-nums">
                        {fmtQuota(plan.max_templates)}
                      </td>
                      <td className="px-6 py-3.5 text-sm text-secondary-foreground tabular-nums">
                        {fmtQuota(plan.max_credentials)}
                      </td>
                      <td className="px-6 py-3.5 text-sm text-secondary-foreground tabular-nums">
                        {ov?.users_by_plan[plan.name] ?? 0}
                      </td>
                      <td className="px-6 py-3.5 text-right">
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); setEditingPlan(plan); }}
                          aria-label={`Edit ${plan.display_name}`}
                          className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                        >
                          <Pencil size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
          )}
          </div>
        </div>

        {/* ── Users ─────────────────────────────────────────────────────── */}
        <div>
          <h2 className="mb-3 text-sm font-semibold text-foreground">Users</h2>
          <FilterBar
            search={
              <SearchInput
                value={search}
                onChange={(v) => { setSearch(v); setPage(1); }}
                placeholder="Search by email…"
              />
            }
            controls={[
              <SegmentedFilter
                key="role"
                label="Role"
                value={roleFilter}
                options={ROLE_OPTIONS}
                onChange={(v) => { setRoleFilter(v); setPage(1); }}
              />,
              <SegmentedFilter
                key="exceeded"
                label="Quota"
                value={exceededFilter}
                options={EXCEEDED_OPTIONS}
                onChange={(v) => { setExceededFilter(v); setPage(1); }}
              />,
            ]}
          />

          <div className={cn(TABLE_CARD, "mt-4")}>
            {usersQuery.isLoading ? (
              <div className="flex h-40 items-center justify-center">
                <Loader2 size={20} className="animate-spin text-muted-foreground" />
              </div>
            ) : users.length === 0 ? (
              <div className="px-6 py-10 text-center text-sm text-muted-foreground">No users found.</div>
            ) : (
                <table className="w-full min-w-[800px]">
                  <thead>
                    <tr className="border-b border-border">
                      <SortableTh label="Email" />
                      <SortableTh label="Role" />
                      <SortableTh label="Status" />
                      <SortableTh label="Recordings" />
                      <SortableTh label="Storage" />
                      <SortableTh label="Quota" />
                      <SortableTh label="Last seen" />
                    </tr>
                  </thead>
                  <tbody className={TABLE_BODY}>
                    {users.map((u) => {
                      const s = statsById.get(u.id);
                      return (
                        <tr
                          key={u.id}
                          onClick={() => setEditingUser(u)}
                          className={cn(TABLE_ROW, "cursor-pointer")}
                        >
                          <td className="px-6 py-3.5">
                            <p
                              title={u.email}
                              className="max-w-[220px] truncate text-sm font-medium text-foreground"
                            >
                              {u.email}
                            </p>
                            <p className="text-xs text-muted-foreground">#{u.user_slug}</p>
                          </td>
                          <td className="px-6 py-3.5"><RoleBadge role={u.role} /></td>
                          <td className="px-6 py-3.5"><StatusBadge active={u.is_active} /></td>
                          <td className="px-6 py-3.5 text-sm tabular-nums text-secondary-foreground">
                            {s ? fmtUsage(s.recordings_used, s.recordings_limit) : "—"}
                          </td>
                          <td className="px-6 py-3.5 text-sm tabular-nums text-secondary-foreground">
                            {s ? `${s.storage_used_gb.toFixed(2)} / ${s.storage_limit_gb === null ? "∞" : s.storage_limit_gb} GB` : "—"}
                          </td>
                          <td className="px-6 py-3.5">
                            {s ? <QuotaBadge exceeding={s.is_exceeding} /> : <span className="text-xs text-muted-foreground">—</span>}
                          </td>
                          <td className="px-6 py-3.5">
                            <span className="text-sm text-muted-foreground">{formatRelative(u.last_login_at)}</span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
            )}
          </div>

          {totalPages > 1 && (
            <div className="mt-4">
              <Pagination
                page={page}
                totalPages={totalPages}
                total={total}
                perPage={PAGE_SIZE}
                onPageChange={setPage}
                itemLabel="user"
              />
            </div>
          )}
        </div>
      </div>

      {/* Modals */}
      <AdminAuditLog />

      {editingUser && (
        <EditUserModal
          user={editingUser}
          plans={plans}
          stats={statsById.get(editingUser.id) ?? null}
          onClose={() => setEditingUser(null)}
          onSaved={handleUserSaved}
          onError={(e) => show("error", e)}
        />
      )}

      {editingPlan !== null && (
        <EditPlanModal
          plan={editingPlan === "new" ? null : editingPlan}
          onClose={() => setEditingPlan(null)}
          onSaved={handlePlanSaved}
          onError={(e) => show("error", e)}
        />
      )}

      {toast && (
        <Toast
          key={toast.serial}
          type={toast.type}
          message={toast.msg}
          exiting={toast.exiting}
          onDismiss={dismiss}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Plan create / edit modal
// ---------------------------------------------------------------------------

function EditPlanModal({
  plan,
  onClose,
  onSaved,
  onError,
}: {
  plan: AdminPlan | null; // null = create new
  onClose: () => void;
  onSaved: () => void;
  onError: (msg: string) => void;
}) {
  const isNew = plan === null;

  const [name, setName] = useState(plan?.name ?? "");
  const [displayName, setDisplayName] = useState(plan?.display_name ?? "");
  const [description, setDescription] = useState(plan?.description ?? "");
  const [isActive, setIsActive] = useState(plan?.is_active ?? true);
  const [quotas, setQuotas] = useState<Record<PlanQuotaKey, string>>(() => {
    const init = {} as Record<PlanQuotaKey, string>;
    for (const f of PLAN_QUOTA_FIELDS) {
      const v = plan?.[f.key];
      init[f.key] = v === null || v === undefined ? "" : String(v);
    }
    return init;
  });

  const save = useMutation({
    mutationFn: async () => {
      const quotaPayload: Record<string, number | null> = {};
      for (const f of PLAN_QUOTA_FIELDS) {
        const raw = quotas[f.key].trim();
        quotaPayload[f.key] = raw === "" ? null : Number(raw);
      }

      if (isNew) {
        if (!name.trim()) throw new Error("Name is required");
        if (!displayName.trim()) throw new Error("Display name is required");
        const body: AdminPlanCreate = {
          name: name.trim(),
          display_name: displayName.trim(),
          description: description.trim() || null,
          is_active: isActive,
          ...quotaPayload,
        };
        await createAdminPlan(body);
      } else {
        const body: AdminPlanUpdate = {
          display_name: displayName.trim(),
          description: description.trim() || null,
          is_active: isActive,
          ...quotaPayload,
        };
        await updateAdminPlan(plan.id, body);
      }
    },
    onSuccess: onSaved,
    onError: (e) => onError(extractApiError(e, "Failed to save plan")),
  });

  return (
    <Modal
      open
      onClose={onClose}
      label={isNew ? "New plan" : `Edit plan — ${plan?.display_name}`}
      panelClassName="max-w-xl"
    >
      <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h2 className="text-base font-semibold text-foreground">
            {isNew ? "New subscription plan" : `Edit — ${plan?.display_name}`}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground"
          >
            <X size={16} />
          </button>
        </div>

        <div className="max-h-[78vh] overflow-y-auto">
          <div className="px-6 pt-5 pb-4 space-y-5">

            <ModalSection title="Identity">
              {isNew && (
                <Field label="Internal name" hint="Unique slug, e.g. free, pro, enterprise. Cannot be changed later.">
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="pro"
                    className={FILTER_CONTROL}
                  />
                </Field>
              )}
              <Field label="Display name">
                <input
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Pro"
                  className={FILTER_CONTROL}
                />
              </Field>
              <Field label="Description" hint="Optional, shown to users.">
                <input
                  type="text"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Full access for professionals"
                  className={FILTER_CONTROL}
                />
              </Field>
              <Toggle label="Active" hint="Inactive plans are hidden from assignment." checked={isActive} onChange={setIsActive} />
            </ModalSection>

            <ModalSection title="Quotas">
              <p className="text-xs text-muted-foreground">
                Leave empty for unlimited (∞). Enter 0 to forbid entirely.
              </p>
              <div className="grid grid-cols-2 gap-3">
                {PLAN_QUOTA_FIELDS.map((f) => (
                  <Field key={f.key} label={f.label}>
                    <input
                      type="number"
                      min={0}
                      inputMode="numeric"
                      value={quotas[f.key]}
                      onChange={(e) => setQuotas((q) => ({ ...q, [f.key]: e.target.value }))}
                      placeholder="∞"
                      className={FILTER_CONTROL}
                    />
                  </Field>
                ))}
              </div>
            </ModalSection>

          </div>

          <div className="flex justify-end gap-2 px-6 py-4 border-t border-border">
            <ActionButton variant="secondary" onClick={onClose}>Cancel</ActionButton>
            <ActionButton variant="primary" isPending={save.isPending} onClick={() => save.mutate()}>
              {isNew ? "Create plan" : "Save changes"}
            </ActionButton>
          </div>
        </div>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// User edit modal
// ---------------------------------------------------------------------------

function EditUserModal({
  user,
  plans,
  stats,
  onClose,
  onSaved,
  onError,
}: {
  user: AdminUserProfile;
  plans: AdminPlan[];
  stats: UserQuotaDetails | null;
  onClose: () => void;
  onSaved: () => void;
  onError: (msg: string) => void;
}) {
  const [role, setRole] = useState(user.role);
  const [isActive, setIsActive] = useState(user.is_active);
  const [isVerified, setIsVerified] = useState(user.is_verified);
  const [perms, setPerms] = useState<Record<PermissionKey, boolean>>(
    () => Object.fromEntries(PERMISSION_FLAGS.map((f) => [f.key, user[f.key]])) as Record<PermissionKey, boolean>,
  );
  const [planId, setPlanId] = useState<number | null>(null);
  const [limits, setLimits] = useState<Record<LimitKey, string>>(
    () => Object.fromEntries(LIMIT_FIELDS.map((f) => [f.key, ""])) as Record<LimitKey, string>,
  );

  const subQuery = useQuery({
    queryKey: ["admin-subscription", user.id],
    queryFn: () => fetchUserSubscription(user.id),
  });

  const sub = subQuery.data?.subscription;
  const hadSubscription = Boolean(sub);
  const effectiveQuotas = subQuery.data?.effective_quotas ?? {};

  // Seed form from loaded subscription
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!sub) return;
    setPlanId(sub.plan_id);
    setLimits(
      Object.fromEntries(
        LIMIT_FIELDS.map((f) => {
          const v = sub[f.key];
          return [f.key, v === null || v === undefined ? "" : String(v)];
        }),
      ) as Record<LimitKey, string>,
    );
  }, [sub]);
  /* eslint-enable react-hooks/set-state-in-effect */

  // Resolve selected plan object to show plan-level defaults as hints
  const selectedPlan = plans.find((p) => p.id === planId) ?? null;

  const save = useMutation({
    mutationFn: async () => {
      await updateAdminUser(user.id, { role, is_active: isActive, is_verified: isVerified, ...perms });
      if (planId !== null) {
        const body: SubscriptionSetBody = { plan_id: planId };
        for (const f of LIMIT_FIELDS) {
          const raw = limits[f.key].trim();
          body[f.key] = raw === "" ? null : Number(raw);
        }
        await setUserSubscription(user.id, body);
      } else if (hadSubscription) {
        await deleteUserSubscription(user.id);
      }
    },
    onSuccess: onSaved,
    onError: (e) => onError(extractApiError(e, "Failed to update user")),
  });

  return (
    <Modal open onClose={onClose} label={`Edit ${user.email}`} panelClassName="max-w-xl">
        {/* Header */}
        <div className="flex items-start justify-between px-6 py-4 border-b border-border">
          <div className="min-w-0 pr-4">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-base font-semibold text-foreground truncate">{user.email}</h2>
              <RoleBadge role={user.role} />
              <StatusBadge active={user.is_active} />
            </div>
            <p className="mt-0.5 text-xs text-muted-foreground">
              #{user.user_slug}
              {" · "}Member since {formatDateTime(user.created_at)}
              {user.last_login_at && <span> · Last seen {formatRelative(user.last_login_at)}</span>}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 p-1.5 rounded-lg hover:bg-muted text-muted-foreground"
          >
            <X size={16} />
          </button>
        </div>

        <div className="max-h-[75vh] overflow-y-auto">
          <div className="px-6 pt-5 pb-4 space-y-4">

            {/* Account */}
            <ModalSection title="Account">
              <Toggle
                label="Email verified"
                hint="Mark email as verified manually (e.g. for internal accounts)."
                checked={isVerified}
                onChange={setIsVerified}
              />
            </ModalSection>

            {/* Actions that change who can get in, or with what powers, are kept
                apart from routine account settings. Both are recorded in the
                audit log. */}
            <div className="rounded-2xl border border-red-200 bg-card shadow-sm">
              <div className="border-b border-red-100 px-6 py-4">
                <h2 className="text-sm font-semibold text-red-600">Danger zone</h2>
              </div>
              <div className="space-y-4 p-6">
                <Field label="Role" hint="Admins can manage every account and plan on the platform.">
                  <NativeSelect value={role} onChange={(e) => setRole(e.target.value)}>
                    <option value="user">user</option>
                    <option value="admin">admin</option>
                  </NativeSelect>
                </Field>
                <Toggle
                  label="Active"
                  hint="Turning this off signs the user out and blocks any further login."
                  checked={isActive}
                  onChange={setIsActive}
                />
              </div>
            </div>

            {/* Permissions */}
            <ModalSection title="Permissions">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-0.5">
                {PERMISSION_FLAGS.map((f) => (
                  <Toggle
                    key={f.key}
                    label={f.label}
                    checked={perms[f.key]}
                    onChange={(v) => setPerms((p) => ({ ...p, [f.key]: v }))}
                  />
                ))}
              </div>
            </ModalSection>

            {/* Usage this month */}
            {stats && (
              <ModalSection title="Usage this month">
                <StatRow
                  label="Recordings"
                  value={fmtUsage(stats.recordings_used, stats.recordings_limit)}
                />
                {stats.recordings_limit !== null && (
                  <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
                    <div
                      className={cn(
                        "h-full rounded-full transition-all",
                        stats.recordings_used > stats.recordings_limit ? "bg-amber-500" : "bg-primary",
                      )}
                      style={{
                        width: `${Math.min(100, (stats.recordings_used / stats.recordings_limit) * 100)}%`,
                      }}
                    />
                  </div>
                )}
                <StatRow
                  label="Storage"
                  value={`${stats.storage_used_gb.toFixed(2)} / ${stats.storage_limit_gb === null ? "∞" : stats.storage_limit_gb} GB`}
                />
                {stats.storage_limit_gb !== null && (
                  <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
                    <div
                      className={cn(
                        "h-full rounded-full transition-all",
                        stats.storage_used_gb > stats.storage_limit_gb ? "bg-amber-500" : "bg-primary",
                      )}
                      style={{
                        width: `${Math.min(100, (stats.storage_used_gb / stats.storage_limit_gb) * 100)}%`,
                      }}
                    />
                  </div>
                )}
                <div className="flex items-center justify-between pt-1">
                  <span className="text-sm text-muted-foreground">Status</span>
                  <QuotaBadge exceeding={stats.is_exceeding} />
                </div>
              </ModalSection>
            )}

            {/* Subscription */}
            <ModalSection title="Plan & limits">
              {subQuery.isLoading ? (
                <div className="flex h-16 items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 size={16} className="animate-spin" /> Loading…
                </div>
              ) : subQuery.isError ? (
                <p className="text-sm text-red-600">Failed to load subscription.</p>
              ) : (
                <>
                  <Field label="Plan">
                    <NativeSelect
                      value={planId ?? ""}
                      onChange={(e) => setPlanId(e.target.value ? Number(e.target.value) : null)}
                    >
                      <option value="">— No subscription —</option>
                      {plans.filter((p) => p.is_active || p.id === planId).map((p) => (
                        <option key={p.id} value={p.id}>{p.display_name}</option>
                      ))}
                    </NativeSelect>
                  </Field>

                  {hadSubscription && planId === null ? (
                    <p className="text-xs text-amber-600 bg-amber-50 dark:bg-amber-500/10 px-3 py-2 rounded-xl">
                      Subscription will be removed on save — user falls back to default (unlimited) quotas.
                    </p>
                  ) : planId !== null ? (
                    <p className="text-xs text-muted-foreground">
                      Per-user overrides. Empty = inherit plan value. 0 = forbid. To give unlimited beyond the plan limit, set the plan field to empty.
                    </p>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      Select a plan to assign a subscription and set per-user limits.
                    </p>
                  )}

                  {planId !== null && (
                    <div className="grid grid-cols-2 gap-3">
                      {LIMIT_FIELDS.map((f) => {
                        const planDefault = selectedPlan ? fmtQuota(selectedPlan[f.planKey as keyof AdminPlan] as number | null) : "∞";
                        const effectiveKey = f.key.replace("custom_", "") as string;
                        const effective = fmtQuota(effectiveQuotas[effectiveKey] as number | null | undefined);
                        return (
                          <Field
                            key={f.key}
                            label={f.label}
                            hint={`Plan: ${planDefault} · Effective: ${effective}`}
                          >
                            <div className="flex gap-1">
                              <input
                                type="number"
                                min={0}
                                inputMode="numeric"
                                value={limits[f.key]}
                                onChange={(e) => setLimits((l) => ({ ...l, [f.key]: e.target.value }))}
                                placeholder="∞"
                                className={cn(FILTER_CONTROL, "flex-1")}
                              />
                              {limits[f.key] !== "" && (
                                <button
                                  type="button"
                                  onClick={() => setLimits((l) => ({ ...l, [f.key]: "" }))}
                                  title="Clear — inherit plan default"
                                  className="shrink-0 h-9 w-9 flex items-center justify-center rounded-lg border border-border text-muted-foreground hover:bg-muted hover:text-foreground transition-colors text-xs font-semibold"
                                >
                                  ∞
                                </button>
                              )}
                            </div>
                          </Field>
                        );
                      })}
                    </div>
                  )}

                  {/* Effective quota summary */}
                  {Object.keys(effectiveQuotas).length > 0 && (
                    <div className="rounded-xl border border-border bg-muted/30 px-4 py-3">
                      <p className="mb-2 text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                        Currently effective
                      </p>
                      {(
                        [
                          ["Recordings / month", "max_recordings_per_month"],
                          ["Storage (GB)", "max_storage_gb"],
                          ["Concurrent tasks", "max_concurrent_tasks"],
                          ["Automation jobs", "max_automation_jobs"],
                          ["Templates", "max_templates"],
                          ["Credentials", "max_credentials"],
                        ] as [string, string][]
                      ).map(([label, key]) => (
                        <StatRow key={key} label={label} value={fmtQuota(effectiveQuotas[key] as number | null | undefined)} />
                      ))}
                    </div>
                  )}
                </>
              )}
            </ModalSection>

          </div>

          <div className="flex justify-end gap-2 px-6 py-4 border-t border-border">
            <ActionButton variant="secondary" onClick={onClose}>Cancel</ActionButton>
            <ActionButton
              variant="primary"
              isPending={save.isPending}
              disabled={subQuery.isLoading}
              onClick={() => save.mutate()}
            >
              Save changes
            </ActionButton>
          </div>
        </div>
    </Modal>
  );
}
