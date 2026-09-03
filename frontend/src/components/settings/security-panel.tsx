"use client";

import { useId, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { LogOut, Monitor, Save, Trash2, X } from "lucide-react";
import { apiClient } from "@/api/client";
import { cn, extractApiError, formatDate, formatRelative } from "@/lib/utils";
import { FILTER_CONTROL, FILTER_LABEL } from "@/lib/filter-field-classes";
import { ActionButton } from "@/components/ui/action-button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { PasswordInput } from "@/components/ui/password-input";
import { PasswordRulesList } from "@/components/ui/password-rules-list";
import { Toast } from "@/components/ui/toast";
import { useToast } from "@/hooks/use-toast";
import { firstFailedRule } from "@/lib/password-rules";
import { TOAST_LONG, TOAST_SHORT } from "@/lib/constants";
import {
  fetchSessions,
  logoutAllDevices,
  logoutOtherDevices,
  revokeSession,
  type SessionInfo,
} from "@/api/sessions";
import { SectionCard } from "./shared";

/**
 * Password field with its own error slot.
 *
 * The message sits next to the field that failed and is wired up with
 * `aria-invalid` + `aria-describedby`, so it is announced rather than being one
 * shared line under all three inputs.
 */
function PasswordField({
  label,
  error,
  below,
  ref,
  ...props
}: {
  label: string;
  error?: string;
  below?: React.ReactNode;
  ref?: React.Ref<HTMLInputElement>;
} & Omit<React.ComponentPropsWithoutRef<"input">, "type">) {
  const id = useId();
  const errorId = `${id}-error`;
  const describedBy = [error ? errorId : null, below ? `${id}-rules` : null].filter(Boolean).join(" ");
  return (
    <div>
      <label htmlFor={id} className={cn(FILTER_LABEL, "mb-1.5")}>{label}</label>
      <PasswordInput
        {...props}
        id={id}
        ref={ref}
        suppressHydrationWarning
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy || undefined}
        className={cn(FILTER_CONTROL, error && "border-danger-fg focus:border-danger-fg focus:ring-danger-fg/30")}
      />
      {error && <p id={errorId} className="mt-1.5 text-xs text-danger-fg">{error}</p>}
      {below && <div id={`${id}-rules`}>{below}</div>}
    </div>
  );
}

export function SecurityPanel() {
  const qc = useQueryClient();
  const router = useRouter();
  const { toast, show: showToast, dismiss: dismissToast } = useToast(TOAST_SHORT);

  const [pwForm, setPwForm] = useState({ current_password: "", new_password: "", confirm: "" });
  // Password feedback stays inline (next to the fields), unlike one-off action
  // confirmations which use toasts — validation/credential errors are clearer
  // when they sit by the form and don't auto-dismiss. Field-level messages sit
  // by the field that failed; `pwError` carries what the server said.
  const [pwError, setPwError] = useState("");
  const [pwFieldErrors, setPwFieldErrors] = useState<{
    current_password?: string;
    new_password?: string;
    confirm?: string;
  }>({});
  const pwCurrentRef = useRef<HTMLInputElement>(null);
  const pwNewRef = useRef<HTMLInputElement>(null);
  const pwConfirmRef = useRef<HTMLInputElement>(null);

  const [deleteAccountOpen, setDeleteAccountOpen] = useState(false);
  const [deleteAccountPassword, setDeleteAccountPassword] = useState("");
  const [deleteAccountError, setDeleteAccountError] = useState("");
  const [logoutAllOpen, setLogoutAllOpen] = useState(false);
  const [logoutOthersOpen, setLogoutOthersOpen] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState<SessionInfo | null>(null);

  const { data: sessions = [], isLoading: sessionsLoading } = useQuery<SessionInfo[]>({
    queryKey: ["auth-sessions"],
    queryFn: fetchSessions,
    refetchOnWindowFocus: true,
  });

  const changePassword = useMutation({
    mutationFn: () =>
      apiClient.post("/users/me/password", {
        current_password: pwForm.current_password,
        new_password: pwForm.new_password,
      }),
    onSuccess: () => {
      setPwError("");
      setPwFieldErrors({});
      showToast("success", "Password changed. All sessions terminated.", TOAST_LONG);
      setPwForm({ current_password: "", new_password: "", confirm: "" });
    },
    onError: (err) => setPwError(extractApiError(err)),
  });

  const logoutAll = useMutation({
    mutationFn: logoutAllDevices,
    onSuccess: () => {
      // Token version was bumped — current cookies are dead. Drop client state
      // and bounce to /login; the 401 interceptor would do this anyway on the
      // next request, but this is snappier UX.
      qc.clear();
      setLogoutAllOpen(false);
      router.push("/login");
    },
  });

  const logoutOthers = useMutation({
    mutationFn: logoutOtherDevices,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["auth-sessions"] });
      setLogoutOthersOpen(false);
      showToast("success", "Signed out from other devices");
    },
    onError: (err) => showToast("error", extractApiError(err), null),
  });

  const revokeOne = useMutation({
    mutationFn: (id: number) => revokeSession(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["auth-sessions"] });
      setRevokeTarget(null);
      showToast("success", "Session revoked");
    },
    onError: (err) => showToast("error", extractApiError(err), null),
  });

  const deleteAccount = useMutation({
    mutationFn: () => apiClient.delete("/users/me", { data: { password: deleteAccountPassword } }),
    onSuccess: () => {
      qc.clear();
      router.push("/login");
    },
    onError: (err) => setDeleteAccountError(extractApiError(err)),
  });

  function handlePasswordSubmit() {
    // Validate everything at once, mark each failing field, then focus the
    // first one — reporting a single error at a time makes the user resubmit to
    // discover the next rule.
    const errors: typeof pwFieldErrors = {};
    if (!pwForm.current_password) errors.current_password = "Enter your current password.";
    const failedRule = firstFailedRule(pwForm.new_password);
    if (failedRule) errors.new_password = `Use a password with: ${failedRule.label.toLowerCase()}.`;
    if (pwForm.new_password !== pwForm.confirm) {
      errors.confirm = "This doesn't match the new password.";
    }

    setPwFieldErrors(errors);
    setPwError("");
    if (errors.current_password) { pwCurrentRef.current?.focus(); return; }
    if (errors.new_password) { pwNewRef.current?.focus(); return; }
    if (errors.confirm) { pwConfirmRef.current?.focus(); return; }

    changePassword.mutate();
  }

  return (
    <div className="space-y-6">
      <SectionCard title="Change password">
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
          <PasswordField
            label="Current password"
            ref={pwCurrentRef}
            autoComplete="current-password"
            value={pwForm.current_password}
            onChange={(e) => setPwForm((p) => ({ ...p, current_password: e.target.value }))}
            placeholder="••••••••"
            error={pwFieldErrors.current_password}
          />
          <PasswordField
            label="New password"
            ref={pwNewRef}
            autoComplete="new-password"
            value={pwForm.new_password}
            onChange={(e) => setPwForm((p) => ({ ...p, new_password: e.target.value }))}
            error={pwFieldErrors.new_password}
            // The policy stays visible instead of living in a placeholder that
            // disappears the moment you start typing.
            below={<PasswordRulesList password={pwForm.new_password} showErrors={!!pwFieldErrors.new_password} />}
          />
          <PasswordField
            label="Confirm new password"
            ref={pwConfirmRef}
            autoComplete="new-password"
            value={pwForm.confirm}
            onChange={(e) => setPwForm((p) => ({ ...p, confirm: e.target.value }))}
            placeholder="Repeat the new password"
            error={pwFieldErrors.confirm}
          />
        </div>
        {pwError && (
          <p role="alert" className="rounded-xl bg-danger-fg/10 px-3 py-2 text-sm text-danger-fg">
            {pwError}
          </p>
        )}
        <div className="flex justify-end">
          <ActionButton
            onClick={handlePasswordSubmit}
            isPending={changePassword.isPending}
            isSuccess={changePassword.isSuccess}
            icon={<Save />}
            pendingLabel="Changing…"
          >
            Change password
          </ActionButton>
        </div>
      </SectionCard>

      <SectionCard title="Active sessions" description="Every device currently signed in to this account.">
        {sessionsLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : sessions.length === 0 ? (
          <p className="text-sm text-muted-foreground">No active sessions.</p>
        ) : (
          <ul className="space-y-2">
            {sessions.map((s) => (
              <li
                key={s.id}
                className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-card px-4 py-3"
              >
                <div className="flex min-w-0 flex-1 items-center gap-3">
                  <div className="shrink-0 rounded-lg bg-muted p-2 text-secondary-foreground">
                    <Monitor size={16} />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="truncate text-sm font-medium text-foreground">
                        {s.device_label || "Unknown device"}
                      </p>
                      {s.is_current && (
                        <span className="rounded-md bg-success-fg/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-success-fg">
                          This device
                        </span>
                      )}
                    </div>
                    {/* Sign-in date, not a second browser string: `device_label`
                        above already names the browser, and the date is what
                        actually tells two sessions of the same browser apart. */}
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {`signed in ${formatDate(s.created_at)} · last active ${formatRelative(s.last_used_at) || "—"}`}
                    </p>
                  </div>
                </div>
                {!s.is_current && (
                  <ActionButton
                    size="sm"
                    variant="secondary"
                    onClick={() => setRevokeTarget(s)}
                    icon={<X />}
                    className="ml-auto shrink-0"
                  >
                    Revoke
                  </ActionButton>
                )}
              </li>
            ))}
          </ul>
        )}

        {/* Sign-out actions live with the sessions they affect. */}
        <div className="flex flex-wrap justify-end gap-2 border-t border-border pt-4">
          <ActionButton
            variant="secondary"
            onClick={() => setLogoutOthersOpen(true)}
            disabled={sessions.length <= 1 || logoutOthers.isPending}
            icon={<LogOut />}
          >
            Sign out other devices
          </ActionButton>
          <ActionButton
            variant="secondary"
            onClick={() => setLogoutAllOpen(true)}
            icon={<LogOut />}
            className="border-danger-fg/65 text-danger-fg hover:bg-danger-fg/10"
          >
            Sign out everywhere
          </ActionButton>
        </div>
      </SectionCard>

      <div className="rounded-2xl border border-danger-fg/30 bg-card shadow-sm">
        <div className="border-b border-danger-fg/20 px-6 py-4">
          <h2 className="text-sm font-semibold text-danger-fg">Danger zone</h2>
        </div>
        <div className="p-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-foreground">Delete account</p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Permanently delete your account and all data. This cannot be undone.
              </p>
            </div>
            <ActionButton
              variant="secondary"
              onClick={() => {
                setDeleteAccountPassword("");
                setDeleteAccountError("");
                setDeleteAccountOpen(true);
              }}
              icon={<Trash2 />}
              className="shrink-0 border-danger-fg/65 text-danger-fg hover:bg-danger-fg/10"
            >
              Delete account
            </ActionButton>
          </div>
        </div>
      </div>

      {/* Session and account confirmations — all share ConfirmDialog, which
          brings the focus trap, ESC handling and scroll lock from Modal. */}
      <ConfirmDialog
        open={logoutAllOpen}
        title="Log out everywhere?"
        description="You will be signed out on every device, including this one."
        confirmLabel="Log out all"
        confirmIcon={<LogOut />}
        pendingLabel="Signing out…"
        isPending={logoutAll.isPending}
        danger
        onConfirm={() => logoutAll.mutate()}
        onCancel={() => setLogoutAllOpen(false)}
      />

      <ConfirmDialog
        open={logoutOthersOpen}
        title="Sign out other devices?"
        description="This device will stay signed in. All other sessions will be revoked."
        confirmLabel="Sign out others"
        confirmIcon={<LogOut />}
        pendingLabel="Signing out…"
        isPending={logoutOthers.isPending}
        onConfirm={() => logoutOthers.mutate()}
        onCancel={() => setLogoutOthersOpen(false)}
      />

      <ConfirmDialog
        open={revokeTarget !== null}
        title="Revoke this session?"
        description={`${revokeTarget?.device_label || "Unknown device"}, signed in ${formatDate(
          revokeTarget?.created_at,
        )}, will be signed out on its next request.`}
        confirmLabel="Revoke"
        confirmIcon={<X />}
        pendingLabel="Revoking…"
        isPending={revokeOne.isPending}
        onConfirm={() => { if (revokeTarget) revokeOne.mutate(revokeTarget.id); }}
        onCancel={() => setRevokeTarget(null)}
      />

      <ConfirmDialog
        open={deleteAccountOpen}
        title="Delete your account?"
        description="This is permanent and irreversible. Enter your password to confirm."
        confirmLabel="Delete permanently"
        confirmIcon={<Trash2 />}
        pendingLabel="Deleting…"
        isPending={deleteAccount.isPending}
        confirmDisabled={!deleteAccountPassword}
        danger
        onConfirm={() => deleteAccount.mutate()}
        onCancel={() => setDeleteAccountOpen(false)}
      >
        <div className="space-y-2">
          <PasswordInput
            autoFocus
            value={deleteAccountPassword}
            onChange={(e) => setDeleteAccountPassword(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && deleteAccountPassword) deleteAccount.mutate();
            }}
            aria-label="Your password"
            placeholder="Your password"
            aria-invalid={deleteAccountError ? true : undefined}
            aria-describedby={deleteAccountError ? "delete-account-error" : undefined}
            className={cn(FILTER_CONTROL, "focus:border-danger-fg focus:ring-danger-fg/30")}
          />
          {deleteAccountError && (
            <p id="delete-account-error" role="alert" className="text-xs text-danger-fg">
              {deleteAccountError}
            </p>
          )}
        </div>
      </ConfirmDialog>

      {toast && (
        <Toast
          key={toast.serial}
          type={toast.type}
          message={toast.msg}
          exiting={toast.exiting}
          onDismiss={dismissToast}
        />
      )}
    </div>
  );
}
