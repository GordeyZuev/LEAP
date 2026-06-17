"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Loader2,
  X,
  Plus,
  RefreshCw,
  AlertCircle,
} from "lucide-react";
import { cn, formatDateTime, formatRelative } from "@/lib/utils";
import { apiClient } from "@/api/client";
import { Toast } from "@/components/ui/toast";
import { ActionButton } from "@/components/ui/action-button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Modal } from "@/components/ui/modal";
import { useToast } from "@/hooks/use-toast";
import { useDebounce } from "@/hooks/use-debounce";
import { FilterBar } from "@/components/filters/filter-bar";
import { SearchInput } from "@/components/filters/search-input";
import { SortControl } from "@/components/filters/sort-control";
import { SegmentedFilter, ACTIVE_STATUS_OPTIONS } from "@/components/filters/segmented-filter";
import { FilterMultiSelect } from "@/components/filters/filter-multi-select";
import { usePlatforms } from "@/hooks/use-references";
import { DEBOUNCE_SEARCH, PER_PAGE_LARGE } from "@/lib/constants";
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
}

const PLATFORMS = [
  { key: "youtube",      label: "YouTube",      oauthPath: "/oauth/youtube/authorize",     hasOAuth: true,  hasManual: false },
  { key: "vk_video",    label: "VK Video",     oauthPath: "/oauth/vk/authorize",          hasOAuth: true,  hasManual: true  },
  { key: "zoom",        label: "Zoom",         oauthPath: "/oauth/zoom/authorize",        hasOAuth: true,  hasManual: true  },
  { key: "yandex_disk", label: "Yandex Disk",  oauthPath: "/oauth/yandex_disk/authorize", hasOAuth: true,  hasManual: true  },
] as const;

type PlatformKey = typeof PLATFORMS[number]["key"];

const PLATFORM_MAP = Object.fromEntries(PLATFORMS.map((p) => [p.key, p])) as Record<
  PlatformKey,
  typeof PLATFORMS[number]
>;

const SORT_OPTIONS = [
  { value: "account_name", label: "Name" },
  { value: "platform",     label: "Platform" },
  { value: "last_used_at", label: "Last used" },
  { value: "created_at",   label: "Created" },
];

type StatusFilter = "all" | "active" | "inactive";
type SortField = "account_name" | "platform" | "last_used_at" | "created_at";

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
};

function sortCredentials(items: CredentialItem[], sortBy: SortField, sortOrder: "asc" | "desc"): CredentialItem[] {
  const sorted = [...items].sort((a, b) => {
    let cmp = 0;
    if (sortBy === "account_name") {
      cmp = (a.account_name ?? "").localeCompare(b.account_name ?? "");
    } else if (sortBy === "platform") {
      cmp = a.platform.localeCompare(b.platform);
    } else if (sortBy === "last_used_at") {
      cmp = (a.last_used_at ?? "").localeCompare(b.last_used_at ?? "");
    } else {
      cmp = a.created_at.localeCompare(b.created_at);
    }
    return sortOrder === "asc" ? cmp : -cmp;
  });
  return sorted;
}

type AddStep = null | "platform" | "connect";

export default function CredentialsPage() {
  const qc = useQueryClient();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data: platformFilterOptions = [] } = usePlatforms();

  // Filter state
  const [searchInput, setSearchInput] = useState("");
  const [platformFilter, setPlatformFilter] = useState<string[]>([]);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sortBy, setSortBy] = useState<SortField>("created_at");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const debouncedSearch = useDebounce(searchInput, DEBOUNCE_SEARCH);

  // Add modal state
  const [addStep, setAddStep] = useState<AddStep>(null);
  const [selectedPlatform, setSelectedPlatform] = useState<PlatformKey | null>(null);
  const [connectTab, setConnectTab] = useState<"oauth" | "manual">("oauth");
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
      qc.invalidateQueries({ queryKey: ["credentials-list"] });
    } else if (error) {
      showToast("error", `${platformLabel} connection failed: ${error.replace(/_/g, " ")}`);
    }
    router.replace("/credentials");
  }, [searchParams, router, showToast, qc]);

  // Disconnect state
  const [disconnectId, setDisconnectId] = useState<number | null>(null);

  const { data: listData, isLoading } = useQuery<CredentialListResponse>({
    queryKey: ["credentials-list"],
    queryFn: async () => {
      const res = await apiClient.get<CredentialListResponse>(`/credentials?per_page=${PER_PAGE_LARGE}`);
      return res.data;
    },
  });

  const disconnect = useMutation({
    mutationFn: (id: number) => apiClient.delete(`/credentials/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["credentials-list"] }),
  });

  const connectManual = useMutation({
    mutationFn: (payload: { platform: string; account_name?: string; credentials: Record<string, string> }) =>
      apiClient.post("/credentials", payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["credentials-list"] });
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
      qc.invalidateQueries({ queryKey: ["credentials-list"] });
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
      window.location.href = url;
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
    setSelectedPlatform(key);
    setConnectTab("oauth");
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

  function resetFilters() {
    setSearchInput("");
    setPlatformFilter([]);
    setStatusFilter("all");
    setSortBy("created_at");
    setSortOrder("desc");
  }

  const hasActiveFilters =
    !!debouncedSearch ||
    platformFilter.length > 0 ||
    statusFilter !== "all" ||
    sortBy !== "created_at" ||
    sortOrder !== "desc";

  const allCredentials = listData?.items ?? [];

  const visibleCredentials = sortCredentials(
    allCredentials.filter((c) => {
      if (debouncedSearch) {
        const q = debouncedSearch.toLowerCase();
        const name = (c.account_name ?? "").toLowerCase();
        const plat = c.platform.toLowerCase();
        if (!name.includes(q) && !plat.includes(q)) return false;
      }
      if (platformFilter.length > 0 && !platformFilter.includes(c.platform)) return false;
      if (statusFilter === "active" && !c.is_active) return false;
      if (statusFilter === "inactive" && c.is_active) return false;
      return true;
    }),
    sortBy,
    sortOrder
  );

  return (
    <div className="w-full min-w-0 p-6 sm:p-8">
      <div className="mb-5 flex min-h-[2.5rem] items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-900">Credentials</h1>
        <ActionButton onClick={openAddModal} icon={<Plus size={15} />}>
          Add
        </ActionButton>
      </div>

      {/* Filters */}
      <FilterBar
        search={
          <SearchInput
            id="creds-search"
            value={searchInput}
            onChange={setSearchInput}
            placeholder="By name or platform…"
          />
        }
        controls={[
          <FilterMultiSelect<string>
            key="platform"
            label="Platform"
            emptySummary="All platforms"
            value={platformFilter}
            options={platformFilterOptions}
            onChange={setPlatformFilter}
          />,
          <SegmentedFilter
            key="status"
            label="Status"
            value={statusFilter}
            options={ACTIVE_STATUS_OPTIONS}
            onChange={(v) => setStatusFilter(v)}
          />,
        ]}
        sort={
          <SortControl
            value={sortBy}
            order={sortOrder}
            options={SORT_OPTIONS}
            onChange={(f) => setSortBy(f as SortField)}
            onToggleOrder={() => setSortOrder((o) => (o === "desc" ? "asc" : "desc"))}
          />
        }
        onClearAll={hasActiveFilters ? resetFilters : undefined}
      />

      {/* Table */}
      <div className="bg-white rounded-2xl border border-[#D9D9D9] shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={20} className="animate-spin text-gray-400" />
          </div>
        ) : allCredentials.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <AlertCircle size={32} className="text-gray-300 mb-3" />
            <p className="text-sm font-medium text-gray-500">No connections yet</p>
            <p className="text-xs text-gray-400 mt-1">Click &ldquo;Add&rdquo; to connect a platform</p>
          </div>
        ) : visibleCredentials.length === 0 ? (
          <div className="py-16 text-center text-sm text-gray-400">No credentials match your filters</div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-[#D9D9D9]">
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Name</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Platform</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Status</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Last used</th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wide">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#D9D9D9]">
              {visibleCredentials.map((cred) => {
                const platform = PLATFORM_MAP[cred.platform as PlatformKey];
                return (
                  <tr key={cred.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-6 py-4">
                      <button
                        onClick={() => openRenameModal(cred)}
                        className="text-sm font-medium text-gray-900 hover:text-[#224C87] transition-colors text-left"
                      >
                        {cred.account_name ?? "—"}
                      </button>
                    </td>
                    <td className="px-6 py-4">
                      <span className="text-sm text-gray-600">{platform?.label ?? cred.platform}</span>
                    </td>
                    <td className="px-6 py-4">
                      <span
                        className={cn(
                          "inline-flex items-center gap-1.5 text-sm",
                          cred.needs_reauth ? "text-amber-600" : cred.is_active ? "text-green-600" : "text-gray-400"
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
                      <span className="text-sm text-gray-400">{formatRelative(cred.last_used_at)}</span>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center justify-end gap-2">
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
                          className="border-red-200 text-red-500 hover:bg-red-50"
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
        )}
      </div>

      {/* Add modal — Step 1: choose platform */}
      <Modal
        open={addStep === "platform"}
        onClose={closeAddModal}
        label="Add connection"
        panelClassName="max-w-md"
      >
        <div className="bg-white">
          <div className="flex items-center justify-between px-6 py-4 border-b border-[#D9D9D9]">
            <h2 className="text-base font-semibold text-gray-900">Add connection</h2>
            <button
              type="button"
              onClick={closeAddModal}
              aria-label="Close dialog"
              className="p-1.5 rounded-lg hover:bg-gray-100"
            >
              <X size={16} />
            </button>
          </div>
          <div className="px-6 py-5">
            <p className="text-sm text-gray-500 mb-4">Choose a platform to connect</p>
            <div className="grid grid-cols-2 gap-3">
              {PLATFORMS.map((p) => (
                <button
                  key={p.key}
                  type="button"
                  onClick={() => selectPlatform(p.key)}
                  className="flex flex-col items-center justify-center gap-2 p-4 rounded-xl border border-[#D9D9D9] hover:border-[#224C87] hover:bg-blue-50/40 transition-colors text-sm font-medium text-gray-700"
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
            label={`Connect ${platform.label}`}
            panelClassName="max-w-md"
          >
            <div className="bg-white">
              <div className="flex items-center justify-between px-6 py-4 border-b border-[#D9D9D9]">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setAddStep("platform")}
                    className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600"
                    aria-label="Back to platform selection"
                  >
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                      <path d="M10 3L5 8L10 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  </button>
                  <h2 className="text-base font-semibold text-gray-900">
                    Connect {platform.label}
                  </h2>
                </div>
                <button
                  type="button"
                  onClick={closeAddModal}
                  aria-label="Close dialog"
                  className="p-1.5 rounded-lg hover:bg-gray-100"
                >
                  <X size={16} />
                </button>
              </div>

              {platform.hasManual && (
                <div className="flex border-b border-[#D9D9D9]">
                  {(["oauth", "manual"] as const).map((tab) => (
                    <button
                      key={tab}
                      onClick={() => { setConnectTab(tab); setFormError(""); }}
                      className={cn(
                        "flex-1 py-2.5 text-sm font-medium transition-colors",
                        connectTab === tab
                          ? "border-b-2 border-[#224C87] text-[#224C87]"
                          : "text-gray-500 hover:text-gray-700"
                      )}
                    >
                      {tab === "oauth" ? "OAuth" : "Manual"}
                    </button>
                  ))}
                </div>
              )}

              <div className="px-6 py-5 space-y-4">
                {connectTab === "oauth" ? (
                  <>
                    <p className="text-sm text-gray-500">
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
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1.5">
                        Connection name <span className="text-gray-400 font-normal">(optional)</span>
                      </label>
                      <input
                        type="text"
                        value={accountName}
                        onChange={(e) => setAccountName(e.target.value)}
                        placeholder="e.g. Main account, Work"
                        className="w-full px-4 py-2.5 rounded-xl border border-[#D9D9D9] text-sm outline-none focus:border-[#224C87] focus:ring-2 focus:ring-[#224C87]/10 transition-colors"
                      />
                    </div>
                    {manualFieldDefs.map((field) => (
                      <div key={field.name}>
                        <label className="block text-sm font-medium text-gray-700 mb-1.5">
                          {field.label}
                        </label>
                        <input
                          type={field.type ?? "text"}
                          value={manualFields[field.name] ?? ""}
                          onChange={(e) =>
                            setManualFields((prev) => ({ ...prev, [field.name]: e.target.value }))
                          }
                          placeholder={field.placeholder}
                          className="w-full px-4 py-2.5 rounded-xl border border-[#D9D9D9] text-sm outline-none focus:border-[#224C87] focus:ring-2 focus:ring-[#224C87]/10 transition-colors"
                        />
                      </div>
                    ))}
                    {formError && (
                      <p className="text-sm text-red-500 bg-red-50 px-3 py-2 rounded-xl">{formError}</p>
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
        return (
          <Modal
            open
            onClose={closeRenameModal}
            label="Connection details"
            panelClassName="max-w-sm"
          >
            <div className="bg-white">
              <div className="flex items-center justify-between px-6 py-4 border-b border-[#D9D9D9]">
                <h2 className="text-base font-semibold text-gray-900">Connection details</h2>
                <button
                  type="button"
                  onClick={closeRenameModal}
                  aria-label="Close dialog"
                  className="p-1.5 rounded-lg hover:bg-gray-100"
                >
                  <X size={16} />
                </button>
              </div>

              <div className="px-6 pt-5 pb-4 space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-xs font-medium text-gray-400 uppercase tracking-wide">Platform</span>
                  <span className="text-sm text-gray-700">{platform?.label ?? cred.platform}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs font-medium text-gray-400 uppercase tracking-wide">Status</span>
                  <span className={cn("inline-flex items-center gap-1.5 text-sm", cred.needs_reauth ? "text-amber-600" : cred.is_active ? "text-green-600" : "text-gray-400")}>
                    {cred.needs_reauth
                      ? <AlertTriangle size={13} className="text-amber-500" />
                      : cred.is_active
                        ? <CheckCircle2 size={13} className="text-green-500" />
                        : <XCircle size={13} className="text-gray-300" />}
                    {cred.needs_reauth ? "Re-auth needed" : cred.is_active ? "Connected" : "Inactive"}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs font-medium text-gray-400 uppercase tracking-wide">Created</span>
                  <span className="text-sm text-gray-700">{formatDateTime(cred.created_at)}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs font-medium text-gray-400 uppercase tracking-wide">Updated</span>
                  <span className="text-sm text-gray-700">{formatDateTime(cred.updated_at)}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs font-medium text-gray-400 uppercase tracking-wide">Last used</span>
                  <span className="text-sm text-gray-700">{cred.last_used_at ? formatDateTime(cred.last_used_at) : "Never"}</span>
                </div>
              </div>

              <div className="mx-6 border-t border-[#D9D9D9]" />

              <div className="px-6 pt-4 pb-5 space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1.5">Name</label>
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
                    className="w-full px-4 py-2.5 rounded-xl border border-[#D9D9D9] text-sm outline-none focus:border-[#224C87] focus:ring-2 focus:ring-[#224C87]/10 transition-colors"
                  />
                </div>
                {renameError && (
                  <p className="text-sm text-red-500 bg-red-50 px-3 py-2 rounded-xl">{renameError}</p>
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
