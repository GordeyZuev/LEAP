"use client";

import { Suspense, useEffect, useRef, useState, type MouseEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Radio, Plus } from "lucide-react";

import { createChannel, listChannels, type ChannelListItem, type ChannelListResponse } from "@/api/channels";
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
import { CARD_INTERACTIVE, CARD_SHELL } from "@/components/ui/section-card";
import { useUrlListState } from "@/hooks/use-url-list-state";
import { CHANNEL_BANNER_FRAME, CHANNEL_BANNER_IMG, PER_PAGE_CHANNELS } from "@/lib/constants";
import { isInitialLoad, listQueryOptions, STALE_TIME } from "@/lib/react-query";
import { cn, extractApiError } from "@/lib/utils";

const GRID_TRACKS = "grid-cols-[repeat(auto-fill,minmax(min(22rem,100%),1fr))]";
const SORT_OPTIONS = [
  { value: "updated_at", label: "Updated" },
  { value: "created_at", label: "Created" },
  { value: "name", label: "Name" },
];
const SORT_ALLOWED = SORT_OPTIONS.map((o) => o.value);
const SHARE_ACTION =
  "inline-flex min-h-7 items-center gap-1 text-xs font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 rounded-sm";

function suggestSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, "-")
    .replace(/^[-_]+|[-_]+$/g, "")
    .slice(0, 64);
}

function sanitizeSlug(raw: string): string {
  return raw.toLowerCase().replace(/[^a-z0-9_-]/g, "").slice(0, 64);
}

function ChannelCard({ channel: c }: { channel: ChannelListItem }) {
  const [copied, setCopied] = useState(false);
  const copiedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const publicShare = c.share_enabled;
  const href = `/c/${c.slug}`;

  useEffect(
    () => () => {
      if (copiedTimer.current) clearTimeout(copiedTimer.current);
    },
    [],
  );

  async function onCopy(e: MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(`${window.location.origin}${href}`);
    } catch {
      return;
    }
    setCopied(true);
    if (copiedTimer.current) clearTimeout(copiedTimer.current);
    copiedTimer.current = setTimeout(() => setCopied(false), 2000);
  }

  return (
    <article className={cn("flex flex-col overflow-hidden p-5", CARD_SHELL, CARD_INTERACTIVE)}>
      <Link href={`/channels/${c.id}`} className="flex min-w-0 flex-col">
        <div
          className={cn(
            CHANNEL_BANNER_FRAME,
            "relative mb-4 rounded-xl",
            "outline outline-1 -outline-offset-1 outline-black/10 dark:outline-white/10",
          )}
        >
          {c.banner_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={c.banner_url} alt="" className={CHANNEL_BANNER_IMG} />
          ) : (
            <div className="flex min-h-24 items-center justify-center text-muted-foreground lg:h-full">
              <Radio size={22} aria-hidden />
            </div>
          )}
        </div>
        <h2 className="truncate text-sm font-semibold leading-snug text-foreground">{c.name}</h2>
      </Link>
      <p className="mt-2 text-xs text-muted-foreground">
        {c.video_count} {c.video_count === 1 ? "video" : "videos"}
        {" · "}
        {c.playlist_count} {c.playlist_count === 1 ? "playlist" : "playlists"}
      </p>
      {publicShare && (
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-0.5">
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className={SHARE_ACTION}
            onClick={(e) => e.stopPropagation()}
          >
            <span className="size-1.5 shrink-0 rounded-full bg-success-fg" aria-hidden />
            <span className="sr-only">{c.name}: </span>
            LEAP
            <span className="sr-only"> public page (active)</span>
            <ExternalLink size={9} strokeWidth={2} className="opacity-40" aria-hidden />
          </a>
          <button type="button" onClick={onCopy} className={SHARE_ACTION}>
            {copied ? "Copied" : "Copy link"}
            <span className="sr-only"> for {c.name}</span>
          </button>
        </div>
      )}
    </article>
  );
}

function ChannelsList() {
  const router = useRouter();
  const qc = useQueryClient();
  const list = useUrlListState({
    defaultSortBy: "updated_at",
    defaultSortOrder: "desc",
    allowedSortFields: SORT_ALLOWED,
  });
  const createFromUrl = list.getParam("create") === "1";
  const setParam = list.setParam;
  const [createOpen, setCreateOpen] = useState(createFromUrl);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  if (createFromUrl && !createOpen) {
    setCreateOpen(true);
  }

  useEffect(() => {
    if (!createFromUrl) return;
    setParam("create", null);
  }, [createFromUrl, setParam]);

  const query = useQuery({
    queryKey: ["channels", list.urlKey],
    queryFn: () =>
      listChannels({
        q: list.search || undefined,
        page: list.page,
        per_page: PER_PAGE_CHANNELS,
        sort_by: list.sortBy,
        sort_order: list.sortOrder,
      }),
    staleTime: STALE_TIME.catalog,
    ...listQueryOptions,
  });

  const create = useMutation({
    mutationFn: () => createChannel({ name: name.trim(), slug: slug.trim() || undefined }),
    onSuccess: (created) => {
      void qc.invalidateQueries({ queryKey: ["channels"] });
      setCreateOpen(false);
      setName("");
      setSlug("");
      setSlugTouched(false);
      router.push(`/channels/${created.id}`);
    },
    onError: (e) => setCreateError(extractApiError(e, "Could not create channel.")),
  });

  const data: ChannelListResponse | undefined = query.data;
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
        title="Channels"
        actions={
          <ActionButton icon={<Plus size={14} />} onClick={() => setCreateOpen(true)}>
            New channel
          </ActionButton>
        }
      />
      <FilterBar
        search={<SearchInput id="channels-search" value={list.searchInput} onChange={list.setSearchInput} placeholder="Name or slug…" />}
        sort={
          <SortControl
            value={list.sortBy}
            order={list.sortOrder}
            options={SORT_OPTIONS}
            onChange={list.setSortField}
            onToggleOrder={list.toggleSortOrder}
          />
        }
        onClearAll={list.hasActiveFilters || list.hasNonDefaultSort ? list.resetAll : undefined}
        chips={<FilterChips chips={chips} />}
      />
      {isInitialLoad(query.isPending, data) && <CardGridSkeleton />}
      {query.isError && <ErrorState description="Could not load channels" onRetry={() => void query.refetch()} />}
      {data && data.items.length === 0 && (
        <EmptyState
          icon={Radio}
          title={list.search ? "No channels match" : "No channels yet"}
          description={list.search ? "Try a different search." : "Create a channel, then add videos and playlists."}
          action={
            !list.search ? (
              <ActionButton size="sm" icon={<Plus size={12} />} onClick={() => setCreateOpen(true)}>
                New channel
              </ActionButton>
            ) : undefined
          }
        />
      )}
      {data && data.items.length > 0 && (
        <>
          <ResultCount total={data.total} itemLabel="channel" filtered={list.hasActiveFilters} />
          <div className={cn("mt-4 grid gap-4", GRID_TRACKS)}>
            {data.items.map((c) => (
              <ChannelCard key={c.id} channel={c} />
            ))}
          </div>
          <Pagination
            page={list.page}
            totalPages={data.total_pages}
            total={data.total}
            perPage={PER_PAGE_CHANNELS}
            onPageChange={list.setPage}
            itemLabel="channel"
          />
        </>
      )}

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} label="New channel" panelClassName="max-w-md">
        <form
          className="space-y-4 p-6"
          onSubmit={(e) => {
            e.preventDefault();
            if (!name.trim() || slug.trim().length < 5) return;
            setCreateError(null);
            create.mutate();
          }}
        >
          <h2 className="text-sm font-semibold text-foreground">New channel</h2>
          <Field label="Name">
            <input
              required
              autoFocus
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setCreateError(null);
                if (!slugTouched) setSlug(suggestSlug(e.target.value));
              }}
              className="w-full rounded-xl border border-border bg-card px-3 py-2.5 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/10"
            />
          </Field>
          <div>
            <Field label="Slug">
              <input
                required
                minLength={5}
                maxLength={64}
                value={slug}
                onChange={(e) => {
                  setSlugTouched(true);
                  setSlug(sanitizeSlug(e.target.value));
                }}
                className="w-full rounded-xl border border-border bg-card px-3 py-2.5 font-mono text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/10"
              />
            </Field>
            <p className="mt-1.5 text-xs text-muted-foreground">
              {slug.length >= 5 ? (
                <>Public URL · <span className="font-mono">/c/{slug}</span></>
              ) : (
                "At least 5 characters. Letters, digits, hyphen, underscore."
              )}
            </p>
          </div>
          {createError && <p className="text-xs text-danger-fg">{createError}</p>}
          <div className="flex justify-end gap-2">
            <ActionButton type="button" variant="secondary" onClick={() => setCreateOpen(false)}>
              Cancel
            </ActionButton>
            <ActionButton type="submit" isPending={create.isPending} disabled={!name.trim() || slug.trim().length < 5}>
              Create channel
            </ActionButton>
          </div>
        </form>
      </Modal>
    </div>
  );
}

export default function ChannelsPage() {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-muted-foreground">Loading channels…</div>}>
      <ChannelsList />
    </Suspense>
  );
}
