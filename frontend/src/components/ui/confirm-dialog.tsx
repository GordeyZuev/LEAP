"use client";

import { useId, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Modal } from "@/components/ui/modal";

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
        <h2 id={titleId} className="text-base font-semibold text-gray-900 mb-2">
          {title}
        </h2>
        <p className="text-sm text-gray-500 mb-4">{description}</p>
        {children && <div className="mb-4">{children}</div>}
        <div className="flex gap-3 justify-end">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 rounded-xl text-sm font-medium border border-[#D9D9D9] text-gray-600 hover:bg-gray-50 transition-colors"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={cn(
              "px-4 py-2 rounded-xl text-sm font-medium transition-colors",
              danger
                ? "bg-red-500 text-white hover:bg-red-600"
                : "bg-[#224C87] text-white hover:bg-[#1a3d6e]",
            )}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </Modal>
  );
}
