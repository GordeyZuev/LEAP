"use client";

import Link from "next/link";
import { Suspense, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Plus, FileText } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/api/client";
import { FilterBar } from "@/components/filters/filter-bar";
import { SearchInput } from "@/components/filters/search-input";
import { SortControl } from "@/components/filters/sort-control";
import { SegmentedFilter, ACTIVE_STATUS_OPTIONS } from "@/components/filters/segmented-filter";
import { Pagination } from "@/components/ui/pagination";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { TableRowsSkeleton } from "@/components/ui/list-skeleton";
import { FilterChips, type FilterChipItem } from "@/components/filters/filter-chips";
import { ResultCount } from "@/components/ui/result-count";
import { SortableTh } from "@/components/ui/sortable-th";
import { useUrlListState } from "@/hooks/use-url-list-state";
import { usePageSize } from "@/hooks/use-page-size";
import { TABLE_BODY, TABLE_CARD, TABLE_ROW } from "@/lib/table-classes";
import { PER_PAGE_TEMPLATES, PER_PAGE_TEMPLATES_OPTIONS } from "@/lib/constants";

interface TemplateListItem {
  id: number;
  name: string;
  description: string | null;
  is_draft: boolean;
  is_active: boolean;
  used_count: number;
  created_at: string;
  updated_at: string;
}

interface TemplateListResponse {
  items: TemplateListItem[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

const SORT_OPTIONS = [
  { value: "created_at", label: "Created" },
  { value: "updated_at", label: "Updated" },
  { value: "name",       label: "Name" },
  { value: "used_count", label: "Used count" },
];

const SORT_ALLOWED = SORT_OPTIONS.map((o) => o.value);

type IsActiveFilter = "all" | "active" | "inactive";

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function TemplatesContent() {
  // Filters live in the URL so a filtered view is shareable and survives reload.
  const list = useUrlListState({
    defaultSortBy: "created_at",
    defaultSortOrder: "desc",
    allowedSortFields: SORT_ALLOWED,
  });
  const { perPage, setPerPage } = usePageSize(
    "templates-per-page",
    PER_PAGE_TEMPLATES_OPTIONS,
    PER_PAGE_TEMPLATES,
  );
  const isActiveFilter: IsActiveFilter =
    list.getParam("is_active") === "true" ? "active"
    : list.getParam("is_active") === "false" ? "inactive"
    : "all";

  const { data, isLoading, error, refetch } = useQuery<TemplateListResponse>({
    queryKey: ["templates", list.urlKey, perPage],
    queryFn: async () => {
      const p = new URLSearchParams();
      if (list.search) p.set("search", list.search);
      if (isActiveFilter !== "all") p.set("is_active", isActiveFilter === "active" ? "true" : "false");
      p.set("sort_by", list.sortBy);
      p.set("sort_order", list.sortOrder);
      p.set("page", String(list.page));
      p.set("per_page", String(perPage));
      const res = await apiClient.get<TemplateListResponse>(`/templates?${p.toString()}`);
      return res.data;
    },
  });

  // Self-correct out-of-range `page` (e.g. after deletes, shared stale links).
  useEffect(() => {
    if (!data) return;
    if (data.total === 0) {
      if (list.page !== 1) list.setPage(1);
    } else if (list.page > data.total_pages) {
      list.setPage(data.total_pages);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, list.page]);

  const templates = data?.items ?? [];
  const sortProps = { sortBy: list.sortBy, sortOrder: list.sortOrder, onSort: list.setSort };

  const chips: FilterChipItem[] = [
    ...(list.search
      ? [{
          key: "search",
          label: `Search: "${list.search}"`,
          onRemove: () => { list.setSearchInput(""); list.setParam("search", null); },
        }]
      : []),
    ...(isActiveFilter !== "all"
      ? [{
          key: "is_active",
          label: isActiveFilter === "active" ? "Active" : "Inactive",
          onRemove: () => list.setParam("is_active", null),
        }]
      : []),
  ];

  return (
    <div className="w-full min-w-0 p-6 sm:p-8">
      <PageHeader
        title="Templates"
        actions={
          <Link
            href="/templates/new"
            className="flex shrink-0 items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-hover"
          >
            <Plus size={16} />
            New template
          </Link>
        }
      />

      {/* Filters */}
      <FilterBar
        search={
          <SearchInput
            id="templates-search"
            value={list.searchInput}
            onChange={list.setSearchInput}
            placeholder="By template name…"
          />
        }
        controls={[
          <SegmentedFilter
            key="status"
            label="Status"
            value={isActiveFilter}
            options={ACTIVE_STATUS_OPTIONS}
            onChange={(v) => list.setParam("is_active", v === "all" ? null : v === "active" ? "true" : "false")}
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

      <ResultCount total={data?.total} itemLabel="template" filtered={list.hasActiveFilters} />

      {/* Table */}
      <div className={TABLE_CARD}>
        <table className="w-full min-w-[640px]">
          <thead>
            <tr className="border-b border-border">
              <SortableTh label="Name" field="name" {...sortProps} />
              <SortableTh label="Status" />
              <SortableTh label="Used" field="used_count" {...sortProps} />
              <SortableTh label="Updated" field="updated_at" {...sortProps} />
            </tr>
          </thead>
          <tbody className={TABLE_BODY}>
            {isLoading && <TableRowsSkeleton rows={5} cols={4} />}
            {error && (
              <tr>
                <td colSpan={4} className="p-0">
                  <ErrorState description="Failed to load templates" onRetry={() => refetch()} />
                </td>
              </tr>
            )}
            {!isLoading && !error && templates.length === 0 && (
              <tr>
                <td colSpan={4} className="p-0">
                  <EmptyState
                    icon={FileText}
                    title={list.hasActiveFilters ? "No templates match your filters" : "No templates yet"}
                    description={
                      list.hasActiveFilters
                        ? "Try adjusting or clearing the filters above."
                        : "Templates define how recordings are matched and named. Create your first one."
                    }
                  />
                </td>
              </tr>
            )}
            {templates.map((t) => (
              <tr key={t.id} className={TABLE_ROW}>
                <td className="px-6 py-4">
                  <div>
                    <Link
                      href={`/templates/${t.id}`}
                      className="text-sm font-medium text-foreground transition-colors hover:text-primary"
                    >
                      {t.name}
                    </Link>
                  </div>
                  {t.description && (
                    <p className="mt-0.5 max-w-xs truncate text-xs text-muted-foreground">{t.description}</p>
                  )}
                </td>
                <td className="px-6 py-4">
                  <span
                    className={cn(
                      "inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium",
                      t.is_draft
                        ? "bg-yellow-100 text-yellow-700 dark:bg-yellow-500/15 dark:text-yellow-300"
                        : t.is_active
                          ? "bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-300"
                          : "bg-muted text-muted-foreground"
                    )}
                  >
                    {t.is_draft ? "Draft" : t.is_active ? "Active" : "Inactive"}
                  </span>
                </td>
                <td className="px-6 py-4 text-sm text-muted-foreground">{t.used_count}×</td>
                <td className="px-6 py-4 text-sm text-muted-foreground">{formatDate(t.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data && (
        <Pagination
          page={list.page}
          totalPages={data.total_pages}
          total={data.total}
          perPage={perPage}
          onPageChange={list.setPage}
          itemLabel="template"
          perPageOptions={PER_PAGE_TEMPLATES_OPTIONS}
          onPerPageChange={(n) => { setPerPage(n); list.setPage(1); }}
          className="mt-5"
        />
      )}
    </div>
  );
}

export default function TemplatesPage() {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-muted-foreground">Loading templates…</div>}>
      <TemplatesContent />
    </Suspense>
  );
}
