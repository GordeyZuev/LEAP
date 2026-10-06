"use client";

import { Suspense, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Mail, MessageSquareText, Newspaper, Plus, Send, Sparkles, TriangleAlert } from "lucide-react";

import {
  deleteAdminProductUpdate,
  fetchAdminProductUpdates,
  fetchProductFeedback,
  fetchProductNewsAudienceCount,
  fetchProductNewsStats,
  INTEREST_OPTIONS,
  publishAdminProductUpdate,
  retryAdminProductUpdate,
  saveAdminProductUpdate,
  sendAdminProductUpdate,
  type AdminProductUpdate,
  type FeedbackKind,
  type ProductUpdateWrite,
} from "@/api/product-updates";
import { useMe } from "@/lib/react-query";
import { useHydrated } from "@/hooks/use-hydrated";
import { extractApiError, formatDate, formatDateTime } from "@/lib/utils";
import { PageHeader } from "@/components/ui/page-header";
import { SectionCard } from "@/components/ui/section-card";
import { AdminSections } from "@/components/admin/admin-sections";
import { ActionButton } from "@/components/ui/action-button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState } from "@/components/ui/empty-state";

const INPUT_CLASS = "w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30";
const EMPTY_DRAFT: ProductUpdateWrite = {
  version: "",
  title: "",
  summary: "",
  audience_bullets: [],
  creator_bullets: [],
  audiences: [],
  newsletter_enabled: false,
};
const FEEDBACK_LABELS: Record<FeedbackKind, string> = {
  idea: "Idea",
  problem: "Problem",
  question: "Question",
  other: "Other",
};

function Metric({ label, value, detail }: { label: string; value: number | string; detail?: string }) {
  return (
    <div className="rounded-2xl border border-border bg-card px-4 py-3 shadow-sm">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums text-foreground">{value}</p>
      {detail && <p className="mt-0.5 text-xs text-muted-foreground">{detail}</p>}
    </div>
  );
}

function AdminUpdatesContent() {
  const qc = useQueryClient();
  const searchParams = useSearchParams();
  const tab = searchParams.get("section") === "feedback" ? "feedback" : "news";
  const [draft, setDraft] = useState<ProductUpdateWrite>(EMPTY_DRAFT);
  const [savedDraft, setSavedDraft] = useState<ProductUpdateWrite>(EMPTY_DRAFT);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [confirmingPublish, setConfirmingPublish] = useState<AdminProductUpdate | null>(null);
  const [confirmingSend, setConfirmingSend] = useState<AdminProductUpdate | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const isDirty = JSON.stringify(draft) !== JSON.stringify(savedDraft);

  const stats = useQuery({ queryKey: ["product-news-stats"], queryFn: fetchProductNewsStats, refetchInterval: 15_000 });
  const updates = useQuery({
    queryKey: ["admin-product-updates"],
    queryFn: fetchAdminProductUpdates,
    enabled: tab === "news",
    refetchInterval: (query) => query.state.data?.some((item) => item.delivery_counts.sending || item.delivery_counts.pending) ? 4_000 : false,
  });
  const feedback = useQuery({
    queryKey: ["admin-product-feedback"],
    queryFn: fetchProductFeedback,
    enabled: tab === "feedback",
  });
  const audienceQuery = useQuery({
    queryKey: ["product-news-audience-count", confirmingSend?.audiences],
    queryFn: () => fetchProductNewsAudienceCount(confirmingSend?.audiences ?? []),
    enabled: Boolean(confirmingSend),
    staleTime: 0,
    refetchOnMount: "always",
  });

  async function refresh() {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ["admin-product-updates"] }),
      qc.invalidateQueries({ queryKey: ["product-news-stats"] }),
      qc.invalidateQueries({ queryKey: ["admin-product-feedback"] }),
    ]);
  }

  const saveMutation = useMutation({
    mutationFn: () => saveAdminProductUpdate(draft, editingId ?? undefined),
    onSuccess: async (saved) => {
      setEditingId(saved.id);
      const nextDraft = {
        version: saved.version ?? "",
        title: saved.title,
        summary: saved.summary,
        audience_bullets: saved.audience_bullets,
        creator_bullets: saved.creator_bullets,
        audiences: saved.audiences,
        newsletter_enabled: saved.newsletter_enabled,
      };
      setDraft(nextDraft);
      setSavedDraft(nextDraft);
      setNotice("Draft saved.");
      setError("");
      await refresh();
    },
    onError: (cause) => setError(extractApiError(cause, "Could not save this update.")),
  });

  const publishMutation = useMutation({
    mutationFn: publishAdminProductUpdate,
    onSuccess: async () => { setConfirmingPublish(null); setNotice("Update published."); setError(""); await refresh(); },
    onError: (cause) => setError(extractApiError(cause, "Could not publish this update.")),
  });

  const sendMutation = useMutation({
    mutationFn: sendAdminProductUpdate,
    onSuccess: async () => { setConfirmingSend(null); setNotice("Newsletter queued. You can follow progress in the update list."); setError(""); await refresh(); },
    onError: (cause) => setError(extractApiError(cause, "Could not queue this newsletter.")),
  });

  const retryMutation = useMutation({
    mutationFn: retryAdminProductUpdate,
    onSuccess: async () => { setNotice("Failed recipients queued for retry."); setError(""); await refresh(); },
    onError: (cause) => setError(extractApiError(cause, "Could not retry this newsletter.")),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteAdminProductUpdate,
    onSuccess: async () => { setEditingId(null); setDraft(EMPTY_DRAFT); setSavedDraft(EMPTY_DRAFT); setNotice("Draft deleted."); await refresh(); },
    onError: (cause) => setError(extractApiError(cause, "Could not delete this draft.")),
  });

  const audienceLabel = useMemo(() => {
    const active = draft.audiences.map((value) => INTEREST_OPTIONS.find((item) => item.value === value)?.label).filter(Boolean);
    return active.length ? active.join(", ") : "All interests";
  }, [draft.audiences]);
  const sendAudienceLabel = useMemo(() => {
    const active = (confirmingSend?.audiences ?? []).map((value) => INTEREST_OPTIONS.find((item) => item.value === value)?.label).filter(Boolean);
    return active.length ? active.join(", ") : "All interests";
  }, [confirmingSend?.audiences]);

  function editUpdate(item: AdminProductUpdate) {
    if (isDirty) {
      setError("Save this draft before switching to another update.");
      return;
    }
    setEditingId(item.id);
    const nextDraft = {
      version: item.version ?? "",
      title: item.title,
      summary: item.summary,
      audience_bullets: item.audience_bullets,
      creator_bullets: item.creator_bullets,
      audiences: item.audiences,
      newsletter_enabled: item.newsletter_enabled,
    };
    setDraft(nextDraft);
    setSavedDraft(nextDraft);
    setNotice("");
    setError("");
  }

  function newDraft() {
    if (isDirty) {
      setError("Save this draft before starting another one.");
      return;
    }
    setEditingId(null);
    setDraft(EMPTY_DRAFT);
    setSavedDraft(EMPTY_DRAFT);
    setNotice("");
    setError("");
  }

  function discardChanges() {
    setDraft({ ...savedDraft, audiences: [...savedDraft.audiences] });
    setError("");
    setNotice("");
  }

  if (tab === "news" && updates.isPending && !updates.data) return <div role="status" className="flex h-64 items-center justify-center text-sm text-muted-foreground">Loading product news tools…</div>;

  return (
    <div className="w-full min-w-0 p-6 sm:p-8">
      <PageHeader
        title={tab === "news" ? "News & email" : "Feedback"}
        description={tab === "news" ? "Publish notable LEAP updates and manage newsletter delivery." : "Review messages sent by LEAP users."}
      />

      <AdminSections>
      {tab === "news" ? <>
      <div className="mb-6 grid grid-cols-2 gap-3 xl:grid-cols-3">
        <Metric label="Confirmed subscriptions" value={stats.data?.subscriptions_confirmed ?? "—"} detail={`Total: ${stats.data?.subscriptions_total ?? "—"} · Pending: ${stats.data?.subscriptions_pending ?? "—"}`} />
        <Metric label="Emails accepted by SMTP" value={stats.data?.delivery_by_status.sent ?? 0} detail="Acceptance does not confirm inbox delivery." />
        <Metric label="Email errors" value={stats.data?.delivery_by_status.failed ?? 0} detail={`Queued: ${stats.data?.delivery_by_status.pending ?? 0}`} />
      </div>
      {stats.isError && <p role="status" className="mb-4 rounded-xl bg-warning-fg/10 px-4 py-3 text-sm text-secondary-foreground">Could not load the communication totals. Refresh the page to try again.</p>}
      <div className="mb-6 rounded-2xl border border-border bg-card p-4 shadow-sm">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Confirmed subscriber interests</p>
          <p className="mt-2 text-xs leading-6 text-secondary-foreground">{INTEREST_OPTIONS.map((option) => `${option.label}: ${stats.data?.interests[option.value] ?? "—"}`).join(" · ")}</p>
          <p className="mt-1 text-[11px] text-muted-foreground">A subscriber can select more than one interest; counts can overlap.</p>
        </div>
      </div>
      </> : <>
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Metric label="Feedback received" value={stats.data?.feedback_total ?? "—"} />
      </div>
      {stats.isError && <p role="status" className="mb-4 rounded-xl bg-warning-fg/10 px-4 py-3 text-sm text-secondary-foreground">Could not load the communication totals. Refresh the page to try again.</p>}
      <div className="mb-6 rounded-2xl border border-border bg-card p-4 shadow-sm">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Feedback by type</p>
          <p className="mt-2 text-xs leading-6 text-secondary-foreground">{Object.entries(stats.data?.feedback_by_kind ?? {}).map(([kind, count]) => `${FEEDBACK_LABELS[kind as FeedbackKind] ?? kind}: ${count}`).join(" · ") || "No feedback yet"}</p>
          <p className="mt-1 text-xs leading-6 text-secondary-foreground">{INTEREST_OPTIONS.map((option) => `${option.label}: ${stats.data?.feedback_by_interest[option.value] ?? "—"}`).join(" · ")}</p>
        </div>
      </div>
      </>}

      {error.startsWith("Product-news email requires") ? (
        <div role="alert" className="mb-4 flex gap-3 rounded-2xl border border-warning-fg/20 bg-warning-fg/[0.04] px-4 py-3.5 text-sm text-secondary-foreground">
          <TriangleAlert size={18} className="mt-0.5 shrink-0 text-warning-fg" />
          <div>
            <p className="font-semibold text-foreground">Product-news email is not ready</p>
            <p className="mt-1 leading-relaxed">Check SMTP settings and set <code className="rounded bg-muted px-1 py-0.5 text-xs">EMAIL_BASE_URL</code> to the public HTTPS frontend address. Localhost addresses cannot be used in subscriber emails.</p>
          </div>
        </div>
      ) : error && <p role="alert" className="mb-4 rounded-xl border border-danger-fg/20 bg-danger-fg/[0.04] px-4 py-3 text-sm text-danger-fg">{error}</p>}
      {notice && <p role="status" className="mb-4 rounded-xl bg-success-fg/10 px-4 py-3 text-sm text-success-fg">{notice}</p>}

      {tab === "news" ? (
        <div className="grid items-start gap-6 xl:grid-cols-[minmax(18rem,0.85fr)_minmax(0,1.3fr)]">
          <SectionCard title="Product updates" description="The public archive is the source for the News links and email content." action={<ActionButton size="sm" onClick={newDraft} icon={<Plus size={14} />}>New draft</ActionButton>}>
            {updates.isError ? (
              <p role="status" className="rounded-xl bg-warning-fg/10 px-3 py-2.5 text-sm text-secondary-foreground">Could not load product updates. Refresh the page to try again.</p>
            ) : updates.data?.length ? (
              <div className="space-y-2">
                {updates.data.map((item) => {
                  const sent = Boolean(item.email_requested_at);
                  const pending = item.delivery_counts.pending ?? 0;
                  const sending = item.delivery_counts.sending ?? 0;
                  const failed = item.delivery_counts.failed ?? 0;
                  const accepted = item.delivery_counts.sent ?? 0;
                  const skipped = item.delivery_counts.skipped ?? 0;
                  return (
                    <article key={item.id} className={`rounded-xl border p-3.5 ${editingId === item.id ? "border-primary/40 bg-primary/[0.03]" : "border-border"}`}>
                      <button type="button" onClick={() => editUpdate(item)} className="w-full text-left">
                        <span className="flex items-start justify-between gap-2">
                          <span className="min-w-0">
                            <span className="block truncate text-sm font-semibold text-foreground">{item.title || "Untitled draft"}</span>
                            <span className="mt-1 block text-xs text-muted-foreground">{item.version ? `v${item.version} · ` : ""}{item.is_published ? item.release_date ? `Released ${formatDate(`${item.release_date}T12:00:00Z`)}` : "Published · release date unknown" : "Draft"}</span>
                          </span>
                          <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${item.is_published ? "bg-success-fg/10 text-success-fg" : "bg-muted text-muted-foreground"}`}>{item.is_published ? "Published" : "Draft"}</span>
                        </span>
                      </button>
                      {sent && <p className="mt-2 text-xs text-muted-foreground">Email · accepted {accepted} · errors {failed}{skipped ? ` · skipped ${skipped}` : ""}{pending || sending ? ` · in progress ${pending + sending}` : ""}</p>}
                      <div className="mt-3 flex flex-wrap gap-2">
                        {!item.is_published && <ActionButton size="sm" variant="secondary" onClick={() => setConfirmingPublish(item)} isPending={publishMutation.isPending} disabled={editingId === item.id && isDirty}>Publish</ActionButton>}
                        {item.is_published && item.newsletter_enabled && !sent && <ActionButton size="sm" variant="secondary" onClick={() => setConfirmingSend(item)} icon={<Send size={13} />} disabled={editingId === item.id && isDirty}>Send email</ActionButton>}
                        {sent && (failed > 0 || pending > 0 || sending > 0) && <ActionButton size="sm" variant="secondary" onClick={() => retryMutation.mutate(item.id)} isPending={retryMutation.isPending}>{failed > 0 ? "Retry errors" : "Resume sending"}</ActionButton>}
                        {!item.is_published && <ActionButton size="sm" variant="danger" onClick={() => deleteMutation.mutate(item.id)} isPending={deleteMutation.isPending} disabled={editingId === item.id && isDirty}>Delete</ActionButton>}
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : <EmptyState icon={Newspaper} title="No product updates yet" description="Create the first draft to start the public news archive." />}
          </SectionCard>

          <div className="space-y-5">
            <SectionCard title={editingId ? "Edit update" : "New update draft"} description="Add a short note, then the release bullets for each group.">
              {isDirty && editingId && <p role="status" className="mb-3 rounded-xl bg-warning-fg/10 px-3 py-2 text-xs text-secondary-foreground">Unsaved changes. Save them before publishing this draft.</p>}
              <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); saveMutation.mutate(); }}>
                <label className="block space-y-1.5"><span className="text-sm font-medium">Version <span className="font-normal text-muted-foreground">(optional)</span></span><input className={INPUT_CLASS} maxLength={32} value={draft.version ?? ""} onChange={(e) => setDraft({ ...draft, version: e.target.value })} placeholder="0.11.1.1" /></label>
                <label className="block space-y-1.5"><span className="text-sm font-medium">Title</span><input required minLength={3} maxLength={180} className={INPUT_CLASS} value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} /></label>
                <label className="block space-y-1.5"><span className="text-sm font-medium">Note</span><textarea required minLength={3} maxLength={300} rows={2} className={`${INPUT_CLASS} resize-y`} value={draft.summary} onChange={(e) => setDraft({ ...draft, summary: e.target.value })} placeholder="What is this update about?" /></label>
                <label className="block space-y-1.5"><span className="text-sm font-medium">For Audience</span><textarea maxLength={6000} rows={4} className={`${INPUT_CLASS} resize-y`} value={draft.audience_bullets.join("\n")} onChange={(e) => setDraft({ ...draft, audience_bullets: e.target.value.split("\n").map((item) => item.trim()).filter(Boolean) })} placeholder="One short bullet per line" /></label>
                <label className="block space-y-1.5"><span className="text-sm font-medium">For Creators</span><textarea maxLength={6000} rows={4} className={`${INPUT_CLASS} resize-y`} value={draft.creator_bullets.join("\n")} onChange={(e) => setDraft({ ...draft, creator_bullets: e.target.value.split("\n").map((item) => item.trim()).filter(Boolean) })} placeholder="One short bullet per line" /></label>
                <fieldset className="space-y-2">
                  <legend className="mb-2 text-sm font-medium">Newsletter audience</legend>
                  <p className="mb-2 text-xs text-muted-foreground">An empty selection means all confirmed subscribers. Public updates remain visible to everyone.</p>
                  {INTEREST_OPTIONS.map((option) => <label key={option.value} className="flex cursor-pointer items-center gap-2.5 text-sm text-secondary-foreground"><input type="checkbox" checked={draft.audiences.includes(option.value)} onChange={(event) => setDraft({ ...draft, audiences: event.target.checked ? [...draft.audiences, option.value] : draft.audiences.filter((value) => value !== option.value) })} className="size-4 accent-primary" />{option.label}</label>)}
                </fieldset>
                <label className="flex cursor-pointer items-start gap-2.5 rounded-xl border border-border p-3 text-sm">
                  <input type="checkbox" checked={draft.newsletter_enabled} onChange={(event) => setDraft({ ...draft, newsletter_enabled: event.target.checked })} className="mt-0.5 size-4 accent-primary" />
                  <span><span className="font-medium text-foreground">Allow an email newsletter for this update</span><span className="mt-0.5 block text-xs leading-relaxed text-muted-foreground">Nothing is sent automatically. After publishing, an administrator must review the audience count and explicitly queue the email.</span></span>
                </label>
                <div className="flex flex-wrap items-center gap-3 border-t border-border pt-4">
                  <ActionButton type="submit" isPending={saveMutation.isPending} pendingLabel="Saving…">Save draft</ActionButton>
                  {isDirty && <ActionButton type="button" variant="secondary" onClick={discardChanges}>Discard changes</ActionButton>}
                  {editingId && <span className="text-xs text-muted-foreground">Audience: {audienceLabel}</span>}
                </div>
              </form>
            </SectionCard>

            <SectionCard title="Preview" description="How the newest public update will read.">
              <div className="rounded-xl border border-primary/15 bg-primary/[0.045] px-4 py-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-primary">News & Updates{draft.version ? ` · v${draft.version}` : ""}</p>
                <p className="mt-1 truncate text-sm font-medium text-foreground">{draft.title || "Update title"}</p>
              </div>
              <p className="text-sm leading-relaxed text-muted-foreground">{draft.summary || "A short note about this update."}</p>
              {(draft.audience_bullets.length > 0 || draft.creator_bullets.length > 0) && <details className="rounded-xl border border-border px-3 py-2 text-sm">
                <summary className="cursor-pointer font-medium text-primary">Release notes</summary>
                <div className="mt-3 grid gap-4 sm:grid-cols-2">
                  {draft.audience_bullets.length > 0 && <section><h3 className="text-xs font-semibold uppercase text-muted-foreground">For Audience</h3><ul className="mt-2 list-disc space-y-1 pl-5">{draft.audience_bullets.map((item, index) => <li key={index}>{item}</li>)}</ul></section>}
                  {draft.creator_bullets.length > 0 && <section><h3 className="text-xs font-semibold uppercase text-muted-foreground">For Creators</h3><ul className="mt-2 list-disc space-y-1 pl-5">{draft.creator_bullets.map((item, index) => <li key={index}>{item}</li>)}</ul></section>}
                </div>
              </details>}
            </SectionCard>
          </div>
        </div>
      ) : (
        <SectionCard title="User feedback" description="Feedback is stored separately from newsletter subscriptions; reply email is optional.">
          {feedback.isError ? (
            <p role="status" className="rounded-xl bg-warning-fg/10 px-3 py-2.5 text-sm text-secondary-foreground">Could not load feedback. Refresh the page to try again.</p>
          ) : feedback.isPending ? (
            <p role="status" className="text-sm text-muted-foreground">Loading feedback…</p>
          ) : feedback.data?.length ? <div className="space-y-3">{feedback.data.map((item) => (
            <article key={item.id} className="rounded-xl border border-border p-4">
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <span className="rounded-full bg-muted px-2.5 py-1 font-medium text-secondary-foreground">{FEEDBACK_LABELS[item.kind]}</span>
                <time dateTime={item.created_at}>{formatDateTime(item.created_at)}</time>
                <span>·</span><span>{item.interests.map((interest) => INTEREST_OPTIONS.find((option) => option.value === interest)?.label ?? interest).join(", ")}</span>
              </div>
              <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-foreground">{item.message}</p>
              {item.reply_email && <a href={`mailto:${encodeURIComponent(item.reply_email)}`} className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:underline"><Mail size={13} />{item.reply_email}</a>}
            </article>
          ))}</div> : <EmptyState icon={MessageSquareText} title="No feedback yet" description="New submissions will appear here." />}
        </SectionCard>
      )}
      </AdminSections>

      <ConfirmDialog
        open={Boolean(confirmingPublish)}
        title="Publish this update?"
        description={confirmingPublish ? `“${confirmingPublish.title}” will appear in the public News archive. This will not send email.` : ""}
        confirmLabel="Publish update"
        isPending={publishMutation.isPending}
        pendingLabel="Publishing…"
        onCancel={() => setConfirmingPublish(null)}
        onConfirm={() => confirmingPublish && publishMutation.mutate(confirmingPublish.id)}
      />
      <ConfirmDialog
        open={Boolean(confirmingSend)}
        title="Send this product update?"
        description={audienceQuery.isError
          ? "Could not verify the recipient count. Close this dialog and try again."
          : `This will queue one email to ${audienceQuery.data ?? "…"} confirmed subscribers in: ${sendAudienceLabel}. It cannot be sent again; failed recipients can be retried.`}
        confirmLabel="Queue newsletter"
        confirmIcon={<Send size={15} />}
        isPending={sendMutation.isPending}
        pendingLabel="Queuing…"
        confirmDisabled={audienceQuery.isPending || audienceQuery.isError || !audienceQuery.data}
        onCancel={() => setConfirmingSend(null)}
        onConfirm={() => confirmingSend && sendMutation.mutate(confirmingSend.id)}
      />
    </div>
  );
}

export default function AdminProductUpdatesPage() {
  return <Suspense fallback={<div className="flex h-64 items-center justify-center text-sm text-muted-foreground">Loading…</div>}><AdminProductUpdatesGate /></Suspense>;
}

function AdminProductUpdatesGate() {
  const hydrated = useHydrated();
  const me = useMe();
  if (!hydrated || (me.isPending && !me.data)) return <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">Loading…</div>;
  if (me.data?.role !== "admin") return <EmptyState icon={Sparkles} title="Access denied" description="This area is restricted to administrators." />;
  return <AdminUpdatesContent />;
}
