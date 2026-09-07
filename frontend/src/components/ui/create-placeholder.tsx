"use client";

import Link from "next/link";
import { Plus } from "lucide-react";

import { cn } from "@/lib/utils";
import { FILTER_CONTROL } from "@/lib/filter-field-classes";

const PLACEHOLDER_CLASS = cn(
  FILTER_CONTROL,
  "pressable flex items-center gap-2 border-dashed text-muted-foreground opacity-70 hover:border-primary/40 hover:opacity-100 hover:text-foreground",
  "transition-[color,background-color,border-color,opacity,scale] duration-150",
);

/** Empty control that matches a select trigger, faded, creates the missing thing. */
export function CreatePlaceholder({
  href,
  onClick,
  label,
  id,
  className,
  "aria-describedby": describedBy,
}: {
  href?: string;
  onClick?: () => void;
  label: string;
  id?: string;
  className?: string;
  "aria-describedby"?: string;
}) {
  const inner = (
    <>
      <Plus size={16} strokeWidth={2} className="shrink-0" aria-hidden />
      <span className="min-w-0 truncate font-medium">{label}</span>
    </>
  );

  if (href) {
    return (
      <Link
        id={id}
        href={href}
        aria-describedby={describedBy}
        className={cn(PLACEHOLDER_CLASS, className)}
      >
        {inner}
      </Link>
    );
  }

  return (
    <button
      type="button"
      id={id}
      aria-describedby={describedBy}
      onClick={onClick}
      className={cn(PLACEHOLDER_CLASS, "text-left", className)}
    >
      {inner}
    </button>
  );
}
