"use client";

import { useId, type ReactNode } from "react";
import { Modal } from "@/components/ui/modal";
import { ActionButton } from "@/components/ui/action-button";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  children?: ReactNode;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = false,
  children,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const titleId = useId();
  return (
    <Modal open={open} onClose={onCancel} labelledBy={titleId} panelClassName="max-w-sm">
      <div className="p-6">
        <h2 id={titleId} className="text-base font-semibold text-foreground mb-2">
          {title}
        </h2>
        <p className="text-sm text-muted-foreground mb-4">{description}</p>
        {children && <div className="mb-4">{children}</div>}
        <div className="flex gap-3 justify-end">
          <ActionButton variant="secondary" onClick={onCancel}>
            {cancelLabel}
          </ActionButton>
          <ActionButton variant={danger ? "danger" : "primary"} onClick={onConfirm}>
            {confirmLabel}
          </ActionButton>
        </div>
      </div>
    </Modal>
  );
}
