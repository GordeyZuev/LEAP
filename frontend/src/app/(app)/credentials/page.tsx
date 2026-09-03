"use client";

import { useCallback, useEffect, useId, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  X,
  Plus,
  PlugZap,
  RefreshCw,
  AlertCircle,
} from "lucide-react";
import { cn, formatDateTime, formatRelative } from "@/lib/utils";
import { apiClient } from "@/api/client";
import { Toast } from "@/components/ui/toast";
import { ActionButton } from "@/components/ui/action-button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Modal } from "@/components/ui/modal";
import { PasswordInput } from "@/components/ui/password-input";
import { SegmentedField } from "@/components/ui/segmented-field";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { FilterChips, type FilterChipItem } from "@/components/filters/filter-chips";
import { Pagination } from "@/components/ui/pagination";
import { ResultCount } from "@/components/ui/result-count";
import { SortableTh } from "@/components/ui/sortable-th";
import { TABLE_BODY, TABLE_CARD, TABLE_ROW } from "@/lib/table-classes";
import { TableRowsSkeleton } from "@/components/ui/list-skeleton";
import { useToast } from "@/hooks/use-toast";
import { useUrlListState } from "@/hooks/use-url-list-state";
import { FilterBar } from "@/components/filters/filter-bar";
import { SearchInput } from "@/components/filters/search-input";
import { SortControl } from "@/components/filters/sort-control";
import { SegmentedFilter, ACTIVE_STATUS_OPTIONS } from "@/components/filters/segmented-filter";
import { FilterMultiSelect } from "@/components/filters/filter-multi-select";
import { usePlatforms } from "@/hooks/use-references";
import { PER_PAGE_CREDENTIALS } from "@/lib/constants";
import { isAllowedOAuthUrl } from "@/lib/auth";

interface CredentialItem {
  id: number;
  platform: string;
  account_name: string | null;
  is_active: boolean;
  needs_reauth: boolean;
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
}

interface CredentialListResponse {
  items: CredentialItem[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

// `connectable: false` keeps a platform known — existing connections still show their
// label and stay filterable — while not offering it for new ones.
const PLATFORMS = [
  { key: "youtube",      label: "YouTube",      oauthPath: "/oauth/youtube/authorize",     hasOAuth: true,  hasManual: false, connectable: true  },
  { key: "vk_video",    label: "VK Video",     oauthPath: "/oauth/vk/authorize",          hasOAuth: true,  hasManual: true,  connectable: false },
  { key: "zoom",        label: "Zoom",         oauthPath: "/oauth/zoom/authorize",        hasOAuth: true,  hasManual: true,  connectable: true  },
  { key: "yandex_disk", label: "Yandex Disk",  oauthPath: "/oauth/yandex_disk/authorize", hasOAuth: true,  hasManual: true,  connectable: true  },
  { key: "mts_link",    label: "MTS Link",     oauthPath: "",                             hasOAuth: false, hasManual: true,  connectable: true  },
] as const;

const CONNECTABLE_PLATFORMS = PLATFORMS.filter((p) => p.connectable);

type PlatformKey = typeof PLATFORMS[number]["key"];

const PLATFORM_MAP = Object.fromEntries(PLATFORMS.map((p) => [p.key, p])) as Record<
  PlatformKey,
  typeof PLATFORMS[number]
>;

// Filter by what can be connected here. `/references/platforms` lists upload
// targets instead, so it would miss input-only platforms like MTS Link.
const PLATFORM_FILTER_OPTIONS = PLATFORMS.map((p) => ({ value: p.key as string, label: p.label }));

const SORT_OPTIONS = [
  { value: "account_name", label: "Name" },
  { value: "platform",     label: "Platform" },
  { value: "status",       label: "Status" },
  { value: "last_used_at", label: "Last used" },
  { value: "created_at",   label: "Created" },
];

const SORT_ALLOWED = SORT_OPTIONS.map((o) => o.value);

interface ManualFieldDef {
  name: string;
  label: string;
  placeholder: string;
  type?: string;
}

const MANUAL_FIELDS: Partial<Record<PlatformKey, ManualFieldDef[]>> = {
  vk_video: [
    { name: "access_token", label: "Access Token", placeholder: "vk1.a.ABC...", type: "password" },
  ],
  zoom: [
    { name: "account_id",    label: "Account ID",    placeholder: "ABC123..." },
    { name: "client_id",     label: "Client ID",     placeholder: "your_client_id" },
    { name: "client_secret", label: "Client Secret", placeholder: "your_client_secret", type: "password" },
  ],
  yandex_disk: [
    { name: "oauth_token", label: "OAuth Token", placeholder: "y0_AgAAAAA...", type: "password" },
  ],
  mts_link: [
    { name: "api_token", label: "API Key", placeholder: "x-auth-token value", type: "password" },
  ],
};

const MANUAL_HINTS: Partial<Record<PlatformKey, string>> = {
  mts_link:
    "Take the API key from your MTS Link admin panel, section Business, then API and webhooks. One key covers the whole organization; you choose which lecturers to sync when you add a source.",
};

type AddStep = null | "platform" | "connect";
type ConnectTab = "oauth" | "manual";

const SOON_BADGE = (
  <span className="rounded-full bg-border/70 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide">
    Soon
  </span>
);

interface CredentialCheckResult {
  status: "ok" | "auth_failed" | "unavailable" | "unsupported";
  detail: string;
  needs_reauth: boolean;
  checked_at: string;
}

const CHECK_SUMMARY: Record<CredentialCheckResult["status"], string> = {
  ok: "Connection is working",
  auth_failed: "The platform rejected these credentials — reconnect them",
  unavailable: "Could not reach the platform, credentials left unchanged",
  unsupported: "This platform has no connection check yet",
};

const CRED_FIELD_CLASS =
  "w-full px-4 py-2.5 rounded-xl border border-border text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/10 transition-colors";

export default function CredentialsPage() {
  const qc = useQueryClient();
  // Ids for dialog titles and fields, so labels name their inputs.
  const idPrefix = useId();
  const router = useRouter();
  const searchParams = useSearchParams();

  // The page list and the unfiltered lookup other pages use are separate cache
  // entries; both have to be refreshed after any credential mutation.
  const invalidateCredentials = useCallback(() => {
    void qc.invalidateQueries({ queryKey: ["credentials-page"] });
    void qc.invalidateQueries({ queryKey: ["credentials-list"] });
  }, [qc]);
  // Only used for the OAuth scopes shown in the detail modal.
  const { data: oauthPlatforms = [] } = usePlatforms();

  // Filters live in the URL so a filtered view is shareable and survives reload.
  const list = useUrlListState({
    defaultSortBy: "created_at",
    defaultSortOrder: "desc",
    allowedSortFields: SORT_ALLOWED,
  });
  const platformFilter = list.getAllParams("platform");
  const statusFilter = list.getParam("status") ?? "all";

  // Add modal state
  const [addStep, setAddStep] = useState<AddStep>(null);
  const [selectedPlatform, setSelectedPlatform] = useState<PlatformKey | null>(null);
  const [connectTab, setConnectTab] = useState<ConnectTab>("oauth");
  const [manualFields, setManualFields] = useState<Record<string, string>>({});
  const [accountName, setAccountName] = useState("");
  const [formError, setFormError] = useState("");

  // Detail / rename modal state
  const [renameModal, setRenameModal] = useState<{ cred: CredentialItem; value: string } | null>(null);
  const [renameError, setRenameError] = useState("");
  const { toast, show: showToast, dismiss: dismissToast } = useToast();

  // Handle OAuth callback result from backend redirect
  useEffect(() => {
    const success = searchParams.get("oauth_success");
    const error = searchParams.get("oauth_error");
    const platform = searchParams.get("platform");
    if (!success && !error) return;
    const platformLabel = platform ? PLATFORM_MAP[platform as PlatformKey]?.label ?? platform : "platform";
    if (success === "true") {
      showToast("success", `${platformLabel} connected`);
      invalidateCredentials();
    } else if (error) {
      showToast("error", `${platformLabel} connection failed: ${error.replace(/_/g, " ")}`);
    }
    router.replace("/credentials");
  }, [searchParams, router, showToast, invalidateCredentials]);

  // Disconnect state
  const [disconnectId, setDisconnectId] = useState<number | null>(null);

  const { data: listData, isLoading } = useQuery<CredentialListResponse>({
    // Distinct from the unfiltered ["credentials-list"] lookup other pages use.
    queryKey: ["credentials-page", list.urlKey],
    queryFn: async () => {
      const p = new URLSearchParams();
      if (list.search) p.set("search", list.search);
      platformFilter.forEach((pl) => p.append("platform", pl));
      if (statusFilter !== "all") p.set("is_active", statusFilter === "active" ? "true" : "false");
      p.set("sort_by", list.sortBy);
      p.set("sort_order", list.sortOrder);
      p.set("page", String(list.page));
      p.set("per_page", String(PER_PAGE_CREDENTIALS));
      const res = await apiClient.get<CredentialListResponse>(`/credentials?${p.toString()}`);
      return res.data;
    },
  });

  const disconnect = useMutation({
    mutationFn: (id: number) => apiClient.delete(`/credentials/${id}`),
    onSuccess: () => invalidateCredentials(),
  });

  const [checkingId, setCheckingId] = useState<number | null>(null);

  const checkConnection = useMutation({
    mutationFn: async (id: number) => {
      setCheckingId(id);
      const res = await apiClient.post<CredentialCheckResult>(`/credentials/${id}/check`);
      return res.data;
    },
    onSuccess: (result) => {
      // "unavailable" is not a verdict on the credential, so it must not read as failure.
      const tone = result.status === "ok" ? "success" : result.status === "auth_failed" ? "error" : "info";
      showToast(tone, CHECK_SUMMARY[result.status] ?? result.detail);
      invalidateCredentials();
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showToast("error", msg ?? "Could not run the check");
    },
    onSettled: () => setCheckingId(null),
  });

  const connectManual = useMutation({
    mutationFn: (payload: { platform: string; account_name?: string; credentials: Record<string, string> }) =>
      apiClient.post("/credentials", payload),
    onSuccess: () => {
      invalidateCredentials();
      closeAddModal();
      showToast("success", "Credential connected");
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setFormError(msg ?? "Failed to save credentials");
    },
  });

  const rename = useMutation({
    mutationFn: ({ id, account_name }: { id: number; account_name: string | null }) =>
      apiClient.patch(`/credentials/${id}`, { account_name }),
    onSuccess: () => {
      invalidateCredentials();
      setRenameModal(null);
      setRenameError("");
      showToast("success", "Credential renamed");
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setRenameError(msg ?? "Failed to rename");
    },
  });

  async function handleOAuthConnect(oauthPath: string) {
    try {
      const res = await apiClient.get<{ authorization_url: string }>(oauthPath);
      const url = res.data?.authorization_url;
      if (!url) {
        showToast("error", "OAuth provider did not return a redirect URL");
        return;
      }
      if (!isAllowedOAuthUrl(url)) {
        showToast("error", "Refused to redirect to an untrusted OAuth host");
        return;
      }
      window.location.assign(url);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showToast("error", msg ?? "Failed to initiate OAuth");
    }
  }

  function openAddModal() {
    setAddStep("platform");
    setSelectedPlatform(null);
    setConnectTab("oauth");
    setManualFields({});
    setAccountName("");
    setFormError("");
  }

  function closeAddModal() {
    setAddStep(null);
    setSelectedPlatform(null);
    setConnectTab("oauth");
    setManualFields({});
    setAccountName("");
    setFormError("");
  }

  function selectPlatform(key: PlatformKey) {
    const target = PLATFORM_MAP[key];

    // Nothing to choose on the next step, so skip straight to the redirect.
    if (!target.hasManual && target.hasOAuth) {
      void handleOAuthConnect(target.oauthPath);
      return;
    }

    setSelectedPlatform(key);
    setConnectTab(target.hasOAuth ? "oauth" : "manual");
    const fields = MANUAL_FIELDS[key] ?? [];
    const initial: Record<string, string> = {};
    fields.forEach((f) => { initial[f.name] = ""; });
    setManualFields(initial);
    setAccountName("");
    setFormError("");
    setAddStep("connect");
  }

  function submitManual() {
    if (!selectedPlatform) return;
    setFormError("");
    const payload: { platform: string; account_name?: string; credentials: Record<string, string> } = {
      platform: selectedPlatform,
      credentials: manualFields,
    };
    if (accountName.trim()) payload.account_name = accountName.trim();
    connectManual.mutate(payload);
  }

  function openRenameModal(cred: CredentialItem) {
    setRenameModal({ cred, value: cred.account_name ?? "" });
    setRenameError("");
  }

  function closeRenameModal() {
    setRenameModal(null);
    setRenameError("");
  }

  // Filtering, sorting and paging are done by the API — the page just renders.
  const credentials = listData?.items ?? [];
  const sortProps = { sortBy: list.sortBy, sortOrder: list.sortOrder, onSort: list.setSort };

  const chips: FilterChipItem[] = [
    ...(list.search
      ? [{
          key: "search",
          label: `Search: "${list.search}"`,
          onRemove: () => { list.setSearchInput(""); list.setParam("search", null); },
        }]
      : []),
    ...platformFilter.map((pl) => ({
      key: `platform:${pl}`,
      label: PLATFORM_MAP[pl as PlatformKey]?.label ?? pl,
      onRemove: () => list.setMultiParam("platform", platformFilter.filter((x) => x !== pl)),
    })),
    ...(statusFilter !== "all"
      ? [{
          key: "status",
          label: statusFilter === "active" ? "Active" : "Inactive",
          onRemove: () => list.setParam("status", null),
        }]
      : []),
  ];

  return (
    <div className="w-full min-w-0 p-6 sm:p-8">
      <PageHeader
        title="Credentials"
        actions={
          <ActionButton onClick={openAddModal} icon={<Plus size={15} />}>
            Add
          </ActionButton>
        }
      />

      {/* Filters */}
      <FilterBar
        search={
          <SearchInput
            id="creds-search"
            value={list.searchInput}
            onChange={list.setSearchInput}
            placeholder="By name or platform…"
          />
        }
        controls={[
          <FilterMultiSelect<string>
            key="platform"
            label="Platform"
            emptySummary="All platforms"
            value={platformFilter}
            options={PLATFORM_FILTER_OPTIONS}
            onChange={(next) => list.setMultiParam("platform", next)}
          />,
          <SegmentedFilter
            key="status"
            label="Status"
            value={statusFilter}
            options={ACTIVE_STATUS_OPTIONS}
            onChange={(v) => list.setParam("status", v === "all" ? null : v)}
          />,
        ]}
        sort={
          <SortControl
            value={list.sortBy}
            order={list.sortOrder}
            options={SORT_OPTIONS}
            onChange={list.setSort}
            onToggleOrder={list.toggleSortOrder}
          />
        }
        onClearAll={list.hasActiveFilters || list.hasNonDefaultSort ? list.resetAll : undefined}
        chips={<FilterChips chips={chips} />}
      />

      <ResultCount total={listData?.total} itemLabel="credential" filtered={list.hasActiveFilters} />

      {/* Table */}
      <div className={TABLE_CARD}>
        {isLoading ? (
          <table className="w-full min-w-[680px]">
            <tbody className={TABLE_BODY}>
              <TableRowsSkeleton rows={5} cols={5} />
            </tbody>
          </table>
        ) : credentials.length === 0 && list.hasActiveFilters ? (
          <EmptyState
            icon={AlertCircle}
            title="No credentials match your filters"
            description="Try adjusting or clearing the filters above."
            action={
              <ActionButton variant="secondary" onClick={list.resetAll}>
                Reset filters
              </ActionButton>
            }
          />
        ) : credentials.length === 0 ? (
          <EmptyState
            icon={AlertCircle}
            title="No connections yet"
            description="Connect a platform account (YouTube, VK, Yandex…) so the pipeline can upload on your behalf."
            action={
              <ActionButton onClick={openAddModal} icon={<Plus size={15} />}>
                Add
              </ActionButton>
            }
          />
        ) : (
          <div className="overflow-x-auto">
          <table className="w-full min-w-[680px]">
            <thead>
              <tr className="border-b border-border">
                <SortableTh className="px-6 py-3" label="Name" field="account_name" {...sortProps} />
                <SortableTh className="px-6 py-3" label="Platform" field="platform" {...sortProps} />
                <SortableTh className="px-6 py-3" label="Status" />
                <SortableTh className="px-6 py-3" label="Last used" field="last_used_at" {...sortProps} />
                <SortableTh className="px-6 py-3 text-right" label="Actions" />
              </tr>
            </thead>
            <tbody className={TABLE_BODY}>
              {credentials.map((cred) => {
                const platform = PLATFORM_MAP[cred.platform as PlatformKey];
                return (
                  <tr key={cred.id} className={TABLE_ROW}>
                    <td className="px-6 py-4">
                      <button
                        onClick={() => openRenameModal(cred)}
                        className="text-sm font-medium text-foreground hover:text-primary transition-colors text-left"
                      >
                        {cred.account_name ?? "—"}
                      </button>
                    </td>
                    <td className="px-6 py-4">
                      <span className="text-sm text-secondary-foreground">{platform?.label ?? cred.platform}</span>
                    </td>
                    <td className="px-6 py-4">
                      <span
                        className={cn(
                          "inline-flex items-center gap-1.5 text-sm",
                          cred.needs_reauth ? "text-amber-600" : cred.is_active ? "text-green-600" : "text-muted-foreground"
                        )}
                      >
                        {cred.needs_reauth ? (
                          <AlertTriangle size={14} className="text-amber-500 shrink-0" />
                        ) : cred.is_active ? (
                          <CheckCircle2 size={14} className="text-green-500 shrink-0" />
                        ) : (
                          <XCircle size={14} className="text-gray-300 shrink-0" />
                        )}
                        {cred.needs_reauth ? "Re-auth needed" : cred.is_active ? "Connected" : "Inactive"}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span className="text-sm text-muted-foreground">{formatRelative(cred.last_used_at)}</span>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center justify-end gap-2">
                        <ActionButton
                          size="sm"
                          variant="secondary"
                          title="Ask the platform whether these credentials still work"
                          onClick={() => checkConnection.mutate(cred.id)}
                          isPending={checkConnection.isPending && checkingId === cred.id}
                          pendingLabel="Checking…"
                          icon={<PlugZap size={12} />}
                        >
                          Check
                        </ActionButton>
                        {platform?.hasOAuth && (
                          <ActionButton
                            size="sm"
                            variant="secondary"
                            title="Re-authenticate (use the same account to refresh the token)"
                            onClick={() => platform && handleOAuthConnect(platform.oauthPath)}
                            icon={<RefreshCw size={12} />}
                          >
                            Re-auth
                          </ActionButton>
                        )}
                        <ActionButton
                          size="sm"
                          variant="secondary"
                          onClick={() => setDisconnectId(cred.id)}
                          icon={<X size={12} />}
                          className="border-danger-fg/65 text-danger-fg hover:bg-danger-fg/10"
                        >
                          Disconnect
                        </ActionButton>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          </div>
        )}
      </div>

      {listData && (
        <Pagination
          page={list.page}
          totalPages={listData.total_pages}
          total={listData.total}
          perPage={PER_PAGE_CREDENTIALS}
          onPageChange={list.setPage}
          itemLabel="credential"
        />
      )}

      {/* Add modal — Step 1: choose platform */}
      <Modal
        open={addStep === "platform"}
        onClose={closeAddModal}
        labelledBy={`${idPrefix}-platform-title`}
        panelClassName="max-w-md max-h-[90vh] overflow-y-auto"
      >
        <div className="bg-card">
          <div className="flex items-center justify-between px-6 py-4 border-b border-border sticky top-0 bg-card">
            <h2 id={`${idPrefix}-platform-title`} className="text-base font-semibold text-foreground">Add connection</h2>
            <button
              type="button"
              onClick={closeAddModal}
              aria-label="Close dialog"
              className="p-1.5 rounded-lg hover:bg-muted"
            >
              <X size={16} />
            </button>
          </div>
          <div className="px-6 py-5">
            <p className="text-sm text-muted-foreground mb-4">Choose a platform to connect</p>
            {/* Same chip row as the source Type selector. */}
            <div className="flex gap-2">
              {CONNECTABLE_PLATFORMS.map((p) => (
                <button
                  key={p.key}
                  type="button"
                  onClick={() => selectPlatform(p.key)}
                  className="flex-1 py-2 rounded-xl text-xs font-medium border transition-colors active:scale-[0.96] bg-card text-secondary-foreground border-border hover:bg-muted"
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </Modal>

      {/* Add modal — Step 2: connect */}
      {addStep === "connect" && selectedPlatform && (() => {
        const platform = PLATFORM_MAP[selectedPlatform];
        const manualFieldDefs = MANUAL_FIELDS[selectedPlatform] ?? [];
        return (
          <Modal
            open
            onClose={closeAddModal}
            labelledBy={`${idPrefix}-connect-title`}
            panelClassName="max-w-md max-h-[90vh] overflow-y-auto"
          >
            <div className="bg-card">
              <div className="flex items-center justify-between px-6 py-4 border-b border-border sticky top-0 bg-card">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setAddStep("platform")}
                    className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-secondary-foreground"
                    aria-label="Back to platform selection"
                  >
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                      <path d="M10 3L5 8L10 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  </button>
                  <h2 id={`${idPrefix}-connect-title`} className="text-base font-semibold text-foreground">
                    Connect {platform.label}
                  </h2>
                </div>
                <button
                  type="button"
                  onClick={closeAddModal}
                  aria-label="Close dialog"
                  className="p-1.5 rounded-lg hover:bg-muted"
                >
                  <X size={16} />
                </button>
              </div>

              <div className="px-6 py-5 space-y-4">
                {/* Platforms without OAuth still show the method, marked Soon, so the
                    two ways to connect read the same everywhere. */}
                {platform.hasManual && (
                  <SegmentedField<ConnectTab>
                    label="Connection method"
                    labelHidden
                    value={connectTab}
                    options={[
                      {
                        value: "oauth",
                        label: "OAuth",
                        disabled: !platform.hasOAuth,
                        badge: platform.hasOAuth ? undefined : SOON_BADGE,
                      },
                      { value: "manual", label: "Manual" },
                    ]}
                    onChange={(tab) => { setConnectTab(tab); setFormError(""); }}
                  />
                )}
                {connectTab === "oauth" ? (
                  <>
                    <p className="text-sm text-muted-foreground">
                      You will be redirected to {platform.label} to authorize access.
                    </p>
                    <ActionButton
                      onClick={() => handleOAuthConnect(platform.oauthPath)}
                      className="w-full justify-center py-2.5"
                    >
                      Connect via OAuth
                    </ActionButton>
                  </>
                ) : (
                  <>
                    {MANUAL_HINTS[selectedPlatform] && (
                      <p className="text-sm text-muted-foreground">{MANUAL_HINTS[selectedPlatform]}</p>
                    )}
                    <div>
                      <label
                        htmlFor={`${idPrefix}-account-name`}
                        className="block text-sm font-medium text-secondary-foreground mb-1.5"
                      >
                        Connection name <span className="text-muted-foreground font-normal">(optional)</span>
                      </label>
                      <input
                        id={`${idPrefix}-account-name`}
                        type="text"
                        value={accountName}
                        onChange={(e) => setAccountName(e.target.value)}
                        placeholder="e.g. Main account, Work"
                        className={CRED_FIELD_CLASS}
                      />
                    </div>
                    {manualFieldDefs.map((field) => {
                      const fieldId = `${idPrefix}-${field.name}`;
                      const setValue = (value: string) =>
                        setManualFields((prev) => ({ ...prev, [field.name]: value }));
                      return (
                        <div key={field.name}>
                          <label
                            htmlFor={fieldId}
                            className="block text-sm font-medium text-secondary-foreground mb-1.5"
                          >
                            {field.label}
                          </label>
                          {field.type === "password" ? (
                            <PasswordInput
                              id={fieldId}
                              value={manualFields[field.name] ?? ""}
                              onChange={(e) => setValue(e.target.value)}
                              placeholder={field.placeholder}
                              className={CRED_FIELD_CLASS}
                            />
                          ) : (
                            <input
                              id={fieldId}
                              type={field.type ?? "text"}
                              value={manualFields[field.name] ?? ""}
                              onChange={(e) => setValue(e.target.value)}
                              placeholder={field.placeholder}
                              className={CRED_FIELD_CLASS}
                            />
                          )}
                        </div>
                      );
                    })}
                    {formError && (
                      <p role="alert" className="rounded-xl bg-danger-fg/10 px-3 py-2 text-sm text-danger-fg">
                        {formError}
                      </p>
                    )}
                    <div className="flex justify-end gap-3 pt-1">
                      <ActionButton variant="secondary" onClick={closeAddModal} className="py-2.5">
                        Cancel
                      </ActionButton>
                      <ActionButton
                        onClick={submitManual}
                        isPending={connectManual.isPending}
                        isSuccess={connectManual.isSuccess}
                        pendingLabel="Saving…"
                        className="px-5 py-2.5"
                      >
                        Save
                      </ActionButton>
                    </div>
                  </>
                )}
              </div>
            </div>
          </Modal>
        );
      })()}

      {/* Detail + rename modal */}
      {renameModal && (() => {
        const { cred, value } = renameModal;
        const platform = PLATFORM_MAP[cred.platform as PlatformKey];
        const platformScopes =
          oauthPlatforms.find((o) => o.value === cred.platform)?.scopes ?? [];
        return (
          <Modal
            open
            onClose={closeRenameModal}
            labelledBy={`${idPrefix}-detail-title`}
            panelClassName="max-w-sm max-h-[90vh] overflow-y-auto"
          >
            <div className="bg-card">
              <div className="flex items-center justify-between px-6 py-4 border-b border-border sticky top-0 bg-card">
                <h2 id={`${idPrefix}-detail-title`} className="text-base font-semibold text-foreground">Connection details</h2>
                <button
                  type="button"
                  onClick={closeRenameModal}
                  aria-label="Close dialog"
                  className="p-1.5 rounded-lg hover:bg-muted"
                >
                  <X size={16} />
                </button>
              </div>

              <div className="px-6 pt-5 pb-4 space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Platform</span>
                  <span className="text-sm text-secondary-foreground">{platform?.label ?? cred.platform}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Status</span>
                  <span className={cn("inline-flex items-center gap-1.5 text-sm", cred.needs_reauth ? "text-amber-600" : cred.is_active ? "text-green-600" : "text-muted-foreground")}>
                    {cred.needs_reauth
                      ? <AlertTriangle size={13} className="text-amber-500" />
                      : cred.is_active
                        ? <CheckCircle2 size={13} className="text-green-500" />
                        : <XCircle size={13} className="text-gray-300" />}
                    {cred.needs_reauth ? "Re-auth needed" : cred.is_active ? "Connected" : "Inactive"}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Created</span>
                  <span className="text-sm text-secondary-foreground">{formatDateTime(cred.created_at)}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Updated</span>
                  <span className="text-sm text-secondary-foreground">{formatDateTime(cred.updated_at)}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Last used</span>
                  <span className="text-sm text-secondary-foreground">{cred.last_used_at ? formatDateTime(cred.last_used_at) : "Never"}</span>
                </div>

                {/* What the connection is actually permitted to do. LEAP
                    publishes on the user's behalf, so this should not be a
                    mystery. Scopes come from the live provider config. */}
                {platformScopes.length > 0 && (
                  <div className="space-y-1.5 pt-1">
                    <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      Access granted
                    </span>
                    <ul className="space-y-1">
                      {platformScopes.map((scope) => (
                        <li key={scope} className="flex items-start gap-1.5 text-xs text-secondary-foreground">
                          <Check size={11} className="mt-0.5 shrink-0 text-green-600" />
                          <span className="break-all font-mono">{scope}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              <div className="mx-6 border-t border-border" />

              <div className="px-6 pt-4 pb-5 space-y-4">
                <div>
                  <label className="block text-sm font-medium text-secondary-foreground mb-1.5">Name</label>
                  <input
                    autoFocus
                    type="text"
                    value={value}
                    onChange={(e) => setRenameModal((prev) => prev ? { ...prev, value: e.target.value } : null)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") rename.mutate({ id: cred.id, account_name: value || null });
                      if (e.key === "Escape") closeRenameModal();
                    }}
                    placeholder="e.g. Main account, Work"
                    className="w-full px-4 py-2.5 rounded-xl border border-border text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/10 transition-colors"
                  />
                </div>
                {renameError && (
                  <p role="alert" className="rounded-xl bg-danger-fg/10 px-3 py-2 text-sm text-danger-fg">
                    {renameError}
                  </p>
                )}
                <div className="flex justify-end gap-3">
                  <ActionButton variant="secondary" onClick={closeRenameModal} className="py-2.5">
                    Cancel
                  </ActionButton>
                  <ActionButton
                    onClick={() => rename.mutate({ id: cred.id, account_name: value || null })}
                    isPending={rename.isPending}
                    isSuccess={rename.isSuccess}
                    pendingLabel="Saving…"
                    className="px-5 py-2.5"
                  >
                    Save
                  </ActionButton>
                </div>
              </div>
            </div>
          </Modal>
        );
      })()}

      <ConfirmDialog
        open={disconnectId !== null}
        title="Disconnect credential?"
        description="The stored token will be removed. Presets linked to this credential will keep their settings but won't be able to upload until you assign a new credential to them."
        confirmLabel="Disconnect"
        cancelLabel="Cancel"
        danger
        onConfirm={() => {
          if (disconnectId !== null) disconnect.mutate(disconnectId);
          setDisconnectId(null);
        }}
        onCancel={() => setDisconnectId(null)}
      />

      {toast && <Toast key={toast.serial} type={toast.type} message={toast.msg} exiting={toast.exiting} onDismiss={dismissToast} />}
    </div>
  );
}
