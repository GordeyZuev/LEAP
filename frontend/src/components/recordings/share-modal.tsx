"use client";

import { useCallback, useState } from "react";
import { Check, ExternalLink, Link as LinkIcon } from "lucide-react";

import { disableShareLink, enableShareLink, rotateShareLink } from "@/api/share";
import { apiClient } from "@/api/client";
import { ShareAnalyticsPanel } from "@/components/recordings/share-analytics-panel";
import { ActionButton } from "@/components/ui/action-button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Modal } from "@/components/ui/modal";
import { Toggle } from "@/components/ui/toggle";
import { cn } from "@/lib/utils";
import type { ShareStatsSummary } from "@/lib/share-stats";

const ACCESS_LINK =
  "inline-flex min-h-7 items-center gap-0.5 text-xs font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 rounded-sm";
const ACCESS_ACTION =
  "inline-flex min-h-7 items-center text-xs font-medium text-muted-foreground transition-colors hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 rounded-sm";

interface ShareModalProps {
  open: boolean;
  onClose: () => void;
  recordingId: number;
  initialToken: string | null;
  initialEnabled: boolean;
  shareStats: ShareStatsSummary | null;
  onShareChange: (token: string | null, enabled: boolean) => void;
  allowVideoDownload: boolean;
  allowFilesDownload: boolean;
  onFlagsChange: (flags: { allow_video_download: boolean; allow_files_download: boolean }) => void;
  onToast: (message: string, variant?: "success" | "error") => void;
}

export function ShareModal({
  open,
  onClose,
  recordingId,
  initialToken,
  initialEnabled,
  shareStats,
  onShareChange,
  allowVideoDownload,
  allowFilesDownload,
  onFlagsChange,
  onToast,
}: ShareModalProps) {
  const [token, setToken] = useState<string | null>(initialToken);
  const [enabled, setEnabled] = useState(initialEnabled);
  const [isEnabling, setIsEnabling] = useState(false);
  const [isCopied, setIsCopied] = useState(false);
  const [rotateConfirm, setRotateConfirm] = useState(false);
  const [isRotating, setIsRotating] = useState(false);
  const [analyticsDays, setAnalyticsDays] = useState<7 | 28>(28);

  const [sourceSnapshot, setSourceSnapshot] = useState({
    open,
    initialToken,
    initialEnabled,
  });
  if (
    open !== sourceSnapshot.open ||
    initialToken !== sourceSnapshot.initialToken ||
    initialEnabled !== sourceSnapshot.initialEnabled
  ) {
    setSourceSnapshot({ open, initialToken, initialEnabled });
    setToken(initialToken);
    setEnabled(initialEnabled);
  }

  const shareUrl = token ? `${window.location.origin}/share/${token}` : null;
  const active = enabled && !!token;
  const showAnalytics =
    Boolean(token) ||
    (shareStats?.view_count ?? 0) > 0 ||
    (shareStats?.download_count ?? 0) > 0;

  const applyShare = useCallback(
    (nextToken: string | null, nextEnabled: boolean) => {
      setToken(nextToken);
      setEnabled(nextEnabled);
      onShareChange(nextToken, nextEnabled);
    },
    [onShareChange],
  );

  const handleEnable = useCallback(async () => {
    setIsEnabling(true);
    try {
      const res = await enableShareLink(recordingId);
      applyShare(res.share_token, true);
      onToast(token ? "Share link enabled" : "Share link created", "success");
    } catch {
      onToast("Failed to enable share link", "error");
    } finally {
      setIsEnabling(false);
    }
  }, [recordingId, token, applyShare, onToast]);

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

  const handleDisable = useCallback(async () => {
    try {
      await disableShareLink(recordingId);
      applyShare(token, false);
      onToast("Share link disabled", "success");
    } catch {
      onToast("Failed to disable link", "error");
    }
  }, [recordingId, token, applyShare, onToast]);

  const handleRotate = useCallback(async () => {
    setIsRotating(true);
    try {
      const res = await rotateShareLink(recordingId);
      applyShare(res.share_token, true);
      onToast("Share link rotated", "success");
      setRotateConfirm(false);
    } catch {
      onToast("Failed to rotate link", "error");
    } finally {
      setIsRotating(false);
    }
  }, [recordingId, applyShare, onToast]);

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

          <div className="rounded-xl border border-border px-3 py-3">
            <p className={cn("text-xs font-medium", active ? "text-success-fg" : "text-muted-foreground")}>
              {active ? "Active" : "Not shared"}
            </p>
            {shareUrl && (
              <p className="mt-1.5 truncate font-mono text-xs text-muted-foreground" title={shareUrl}>
                {shareUrl}
              </p>
            )}
            {!enabled && (
              <div className="mt-3">
                <ActionButton
                  size="sm"
                  variant="primary"
                  icon={<LinkIcon size={12} />}
                  isPending={isEnabling}
                  onClick={handleEnable}
                  className="w-full justify-center"
                >
                  Enable link
                </ActionButton>
              </div>
            )}
            {(active || token) && (
              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-0.5">
                {active && shareUrl && (
                  <>
                    <button type="button" onClick={handleCopy} className={ACCESS_LINK}>
                      {isCopied ? (
                        <>
                          <Check size={10} aria-hidden />
                          Copied
                        </>
                      ) : (
                        "Copy"
                      )}
                    </button>
                    <a href={shareUrl} target="_blank" rel="noopener noreferrer" className={ACCESS_LINK}>
                      Open <ExternalLink size={10} aria-hidden />
                    </a>
                    <button type="button" onClick={handleDisable} className={ACCESS_ACTION}>
                      Disable link
                    </button>
                  </>
                )}
                {token && (
                  <button type="button" onClick={() => setRotateConfirm(true)} className={ACCESS_ACTION}>
                    Rotate link
                  </button>
                )}
              </div>
            )}
            <p className="mt-3 text-xs leading-snug text-muted-foreground">
              {active
                ? "Students watch this recording here. Disable keeps the same URL."
                : token
                  ? "Enabling again uses the same URL."
                  : "One URL for this recording."}
            </p>
          </div>

          <div className="mt-4 space-y-1 rounded-xl border border-border px-3 py-2">
            <Toggle
              label="Allow video download"
              hint="Shows a download button for the processed video. Playback cannot be copy-proof."
              checked={allowVideoDownload}
              onChange={(v) => {
                onFlagsChange({ allow_video_download: v, allow_files_download: allowFilesDownload });
                void apiClient.patch(`/recordings/${recordingId}`, { allow_video_download: v }).catch(() => {
                  onToast("Failed to update download settings", "error");
                });
              }}
            />
            <Toggle
              label="Allow file download"
              hint="Shows transcript and subtitle files. Captions in the player still work."
              checked={allowFilesDownload}
              onChange={(v) => {
                onFlagsChange({ allow_video_download: allowVideoDownload, allow_files_download: v });
                void apiClient.patch(`/recordings/${recordingId}`, { allow_files_download: v }).catch(() => {
                  onToast("Failed to update download settings", "error");
                });
              }}
            />
          </div>

          {showAnalytics && (
            <section className="mt-6 rounded-2xl border border-border bg-muted/20 p-4 sm:p-5">
              <ShareAnalyticsPanel
                recordingId={recordingId}
                open={open}
                days={analyticsDays}
                onDaysChange={setAnalyticsDays}
                showRevokedBanner={!enabled && showAnalytics}
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
        open={rotateConfirm}
        title="Rotate share link?"
        description="The current URL will stop working immediately. Anyone with the old link loses access. View and download history stays on this recording."
        confirmLabel="Rotate link"
        cancelLabel="Cancel"
        danger
        isPending={isRotating}
        onConfirm={handleRotate}
        onCancel={() => setRotateConfirm(false)}
      />
    </>
  );
}
