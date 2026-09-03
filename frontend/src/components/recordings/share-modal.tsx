"use client";

import { useCallback, useState } from "react";
import { Check, Copy, ExternalLink, Link, Trash2 } from "lucide-react";

import { createShareLink, revokeShareLink } from "@/api/share";
import { ShareAnalyticsPanel } from "@/components/recordings/share-analytics-panel";
import { ActionButton } from "@/components/ui/action-button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Modal } from "@/components/ui/modal";
import type { ShareStatsSummary } from "@/lib/share-stats";

interface ShareModalProps {
  open: boolean;
  onClose: () => void;
  recordingId: number;
  initialToken: string | null;
  shareStats: ShareStatsSummary | null;
  onTokenChange: (token: string | null) => void;
  onToast: (message: string, variant?: "success" | "error") => void;
}

export function ShareModal({
  open,
  onClose,
  recordingId,
  initialToken,
  shareStats,
  onTokenChange,
  onToast,
}: ShareModalProps) {
  const [token, setToken] = useState<string | null>(initialToken);
  const [isCreating, setIsCreating] = useState(false);
  const [isCopied, setIsCopied] = useState(false);
  const [revokeConfirm, setRevokeConfirm] = useState(false);
  const [isRevoking, setIsRevoking] = useState(false);
  const [analyticsDays, setAnalyticsDays] = useState<7 | 28>(28);

  const shareUrl = token ? `${window.location.origin}/share/${token}` : null;
  const showAnalytics =
    Boolean(token) ||
    (shareStats?.view_count ?? 0) > 0 ||
    (shareStats?.download_count ?? 0) > 0;

  const handleCreate = useCallback(async () => {
    setIsCreating(true);
    try {
      const res = await createShareLink(recordingId);
      setToken(res.share_token);
      onTokenChange(res.share_token);
      onToast("Share link created", "success");
    } catch {
      onToast("Failed to create share link", "error");
    } finally {
      setIsCreating(false);
    }
  }, [recordingId, onTokenChange, onToast]);

  const handleCopy = useCallback(async () => {
    if (!shareUrl) return;
    try {
      await navigator.clipboard.writeText(shareUrl);
      setIsCopied(true);
      onToast("Link copied to clipboard", "success");
      setTimeout(() => setIsCopied(false), 2000);
    } catch {
      onToast("Failed to copy", "error");
    }
  }, [shareUrl, onToast]);

  const handleRevoke = useCallback(async () => {
    setIsRevoking(true);
    try {
      await revokeShareLink(recordingId);
      setToken(null);
      onTokenChange(null);
      onToast("Share link revoked", "success");
      setRevokeConfirm(false);
    } catch {
      onToast("Failed to revoke link", "error");
    } finally {
      setIsRevoking(false);
    }
  }, [recordingId, onTokenChange, onToast]);

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        label="Share recording"
        panelClassName={showAnalytics ? "max-w-lg" : "max-w-md"}
      >
        <div className="max-h-[min(90vh,44rem)] overflow-y-auto p-6">
          <h2 className="mb-1 text-sm font-semibold text-foreground">Share recording</h2>
          <p className="mb-4 text-xs text-muted-foreground">
            Anyone with the link can view the video, chapters, and download files.
          </p>

          {!token ? (
            <div className="flex flex-col gap-3">
              <p className="text-xs text-muted-foreground">No public link yet.</p>
              <ActionButton
                variant="primary"
                isPending={isCreating}
                pendingLabel="Creating…"
                icon={<Link size={13} />}
                onClick={handleCreate}
                className="w-full justify-center"
              >
                Create share link
              </ActionButton>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              <div className="flex items-center gap-2 rounded-xl border border-border bg-muted/40 px-3 py-2">
                <input
                  readOnly
                  value={shareUrl ?? ""}
                  aria-label="Share link URL"
                  className="min-w-0 flex-1 bg-transparent text-xs text-foreground outline-none"
                  onFocus={(e) => e.target.select()}
                />
              </div>
              <div className="flex gap-2">
                <ActionButton
                  variant="secondary"
                  icon={isCopied ? <Check size={13} /> : <Copy size={13} />}
                  onClick={handleCopy}
                  className="flex-1 justify-center"
                >
                  {isCopied ? "Copied!" : "Copy"}
                </ActionButton>
                <ActionButton
                  variant="secondary"
                  icon={<ExternalLink size={13} />}
                  onClick={() => window.open(shareUrl!, "_blank")}
                  className="flex-1 justify-center"
                >
                  Open
                </ActionButton>
              </div>
              <ActionButton
                variant="secondary"
                isPending={isRevoking}
                pendingLabel="Revoking…"
                icon={<Trash2 size={13} />}
                onClick={() => setRevokeConfirm(true)}
                className="w-full justify-center border-danger-fg/65 text-danger-fg hover:bg-danger-fg/10"
              >
                Revoke link
              </ActionButton>
            </div>
          )}

          {showAnalytics && (
            <section className="mt-6 rounded-2xl border border-border bg-muted/20 p-4 sm:p-5">
              <ShareAnalyticsPanel
                recordingId={recordingId}
                open={open}
                days={analyticsDays}
                onDaysChange={setAnalyticsDays}
                showRevokedBanner={!token && showAnalytics}
              />
            </section>
          )}

          <div className="mt-4">
            <ActionButton variant="secondary" onClick={onClose} className="w-full justify-center">
              Close
            </ActionButton>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        open={revokeConfirm}
        title="Revoke share link?"
        description="Anyone with this link loses access immediately. View and download history stays on this recording."
        confirmLabel="Revoke link"
        cancelLabel="Cancel"
        danger
        onConfirm={handleRevoke}
        onCancel={() => setRevokeConfirm(false)}
      />
    </>
  );
}
