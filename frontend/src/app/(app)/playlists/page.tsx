"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ListVideo, Plus } from "lucide-react";

import { createPlaylist, listPlaylists, type PlaylistListResponse } from "@/api/playlists";
import { FilterBar } from "@/components/filters/filter-bar";
import { SearchInput } from "@/components/filters/search-input";
import { SortControl } from "@/components/filters/sort-control";
import { FilterChips, type FilterChipItem } from "@/components/filters/filter-chips";
import { ActionButton } from "@/components/ui/action-button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { CardGridSkeleton } from "@/components/ui/list-skeleton";
import { Modal } from "@/components/ui/modal";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { ResultCount } from "@/components/ui/result-count";
import { Field } from "@/components/ui/field";
import { useUrlListState } from "@/hooks/use-url-list-state";
import { PER_PAGE_PLAYLISTS } from "@/lib/constants";
import { cn, extractApiError } from "@/lib/utils";

const GRID_TRACKS = "grid-cols-[repeat(auto-fill,minmax(min(22rem,100%),1fr))]";

const SORT_OPTIONS = [
  { value: "updated_at", label: "Updated" },
  { value: "created_at", label: "Created" },
  { value: "name", label: "Name" },
];
const SORT_ALLOWED = SORT_OPTIONS.map((o) => o.value);

function formatPlaylistDuration(seconds: number): string {
  if (!seconds || seconds < 0) return "0m";
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  if (h > 0 && m > 0) return `${h}h ${m}m`;
  if (h > 0) return `${h}h`;
  return `${Math.max(m, 0)}m`;
}

function PlaylistsGrid({
  list,
}: {
  list: ReturnType<typeof useUrlListState>;
}) {
  const page = list.page;
  const onPageChange = list.setPage;

  const { data, isLoading, error, refetch } = useQuery<PlaylistListResponse>({
    queryKey: ["playlists", list.urlKey],
    queryFn: () =>
      listPlaylists({
        q: list.search || undefined,
        page,
        per_page: PER_PAGE_PLAYLISTS,
        sort_by: list.sortBy,
        sort_order: list.sortOrder,
      }),
  });

  useEffect(() => {
    if (!data) return;
    if (data.total === 0) {
      if (page !== 1) onPageChange(1);
    } else if (page > data.total_pages) {
      onPageChange(data.total_pages);
    }
  }, [data, page, onPageChange]);

  const playlists = data?.items ?? [];

  return (
    <>
      <ResultCount total={data?.total} itemLabel="playlist" filtered={list.hasActiveFilters} />

      {isLoading && <CardGridSkeleton />}

      {error && <ErrorState description="Failed to load playlists" onRetry={() => void refetch()} />}

      {!isLoading && !error && playlists.length === 0 && (
        list.hasActiveFilters ? (
          <EmptyState
            icon={ListVideo}
            title="No playlists match"
            description="Try a different name, or clear the search."
            action={
              <ActionButton size="sm" variant="secondary" onClick={list.resetAll}>
                Clear filters
              </ActionButton>
            }
          />
        ) : (
          <EmptyState
            icon={ListVideo}
            title="No playlists yet"
            description="Create a playlist, then add recordings from Publications."
          />
        )
      )}

      {!isLoading && !error && playlists.length > 0 && (
        <div className={cn("grid animate-fade-in gap-4", GRID_TRACKS)}>
          {playlists.map((p) => (
            <Link
              key={p.id}
              href={`/playlists/${p.id}`}
              className="flex flex-col overflow-hidden rounded-2xl border border-border bg-card p-5 shadow-sm transition-all hover:border-primary/30 hover:shadow-md"
            >
              <div className="mb-4 aspect-video overflow-hidden rounded-xl bg-muted">
                {p.poster_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={p.poster_url} alt="" className="h-full w-full object-cover" />
                ) : (
                  <div className="flex h-full items-center justify-center text-muted-foreground">
                    <ListVideo size={28} strokeWidth={1.5} />
                  </div>
                )}
              </div>
              <h2 className="line-clamp-2 text-sm font-semibold leading-snug text-balance text-foreground">{p.name}</h2>
              {p.description && (
                <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-pretty text-muted-foreground">{p.description}</p>
              )}
              <p className="mt-2 text-xs text-muted-foreground">
                {p.video_count} {p.video_count === 1 ? "video" : "videos"}
                {" · "}
                {formatPlaylistDuration(p.duration_sum)}
              </p>
              {p.share_enabled && (
                <p className="mt-2 flex items-center gap-1.5 text-xs font-medium text-success-fg">
                  <span className="size-1.5 rounded-full bg-success-fg" aria-hidden />
                  Public
                </p>
              )}
            </Link>
          ))}
        </div>
      )}

      {data && (
        <Pagination
          page={page}
          totalPages={data.total_pages}
          total={data.total}
          perPage={PER_PAGE_PLAYLISTS}
          onPageChange={onPageChange}
          itemLabel="playlist"
        />
      )}
    </>
  );
}

function PlaylistsContent() {
  const router = useRouter();
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);

  const list = useUrlListState({
    defaultSortBy: "updated_at",
    defaultSortOrder: "desc",
    allowedSortFields: SORT_ALLOWED,
  });

  const create = useMutation({
    mutationFn: () => createPlaylist({ name: name.trim(), description: description.trim() || null }),
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["playlists"] });
      setCreateOpen(false);
      setName("");
      setDescription("");
      router.push(`/playlists/${created.id}`);
    },
    onError: (e) => {
      const msg = extractApiError(e, "Failed to create playlist");
      setFieldError(msg.includes("already exists") ? "A playlist with this name already exists." : msg);
    },
  });

  const chips: FilterChipItem[] = list.search
    ? [{
        key: "search",
        label: `Search: "${list.search}"`,
        onRemove: () => { list.setSearchInput(""); list.setParam("search", null); },
      }]
    : [];

  return (
    <div className="w-full min-w-0 p-6 sm:p-8">
      <PageHeader
        title="Playlists"
        actions={
          <ActionButton variant="primary" icon={<Plus size={16} />} onClick={() => { setFieldError(null); setCreateOpen(true); }}>
            Create playlist
          </ActionButton>
        }
      />

      <FilterBar
        search={
          <SearchInput
            id="playlists-search"
            value={list.searchInput}
            onChange={list.setSearchInput}
            placeholder="By name…"
          />
        }
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

      <PlaylistsGrid list={list} />

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} label="Create playlist" panelClassName="max-w-md">
        <form
          className="space-y-4 p-6"
          onSubmit={(e) => {
            e.preventDefault();
            if (!name.trim()) return;
            create.mutate();
          }}
        >
          <h2 className="text-sm font-semibold text-foreground">Create playlist</h2>
          <Field label="Name">
            <input
              required
              value={name}
              onChange={(e) => { setName(e.target.value); setFieldError(null); }}
              className="w-full rounded-xl border border-border bg-card px-3 py-2.5 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/10"
            />
            {fieldError && <p className="mt-1.5 text-xs text-danger-fg">{fieldError}</p>}
          </Field>
          <Field label="Description" hint="Optional">
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full rounded-xl border border-border bg-card px-3 py-2.5 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/10"
            />
          </Field>
          <div className="flex justify-end gap-2">
            <ActionButton type="button" variant="secondary" onClick={() => setCreateOpen(false)}>
              Cancel
            </ActionButton>
            <ActionButton type="submit" isPending={create.isPending} disabled={!name.trim()}>
              Create playlist
            </ActionButton>
          </div>
        </form>
      </Modal>
    </div>
  );
}

export default function PlaylistsPage() {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-muted-foreground">Loading playlists…</div>}>
      <PlaylistsContent />
    </Suspense>
  );
}
