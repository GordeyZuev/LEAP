"use client";

import { KeyboardEvent, useState } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface TagInputProps {
  tags: string[] | null | undefined;
  onChange: (tags: string[]) => void;
  placeholder?: string;
  className?: string;
  /** Applied to the inner text input so an external <label htmlFor> resolves. */
  id?: string;
  "aria-describedby"?: string;
}

export function TagInput({
  tags: tagsProp,
  onChange,
  placeholder = "Add tag…",
  className,
  id,
  "aria-describedby": describedBy,
}: TagInputProps) {
  const tags = tagsProp ?? [];
  const [input, setInput] = useState("");

  function addTag(value: string) {
    const trimmed = value.trim().replace(/,+$/, "");
    if (!trimmed || tags.includes(trimmed)) return;
    onChange([...tags, trimmed]);
    setInput("");
  }

  function handleKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      addTag(input);
    } else if (e.key === "Backspace" && !input && tags.length > 0) {
      onChange(tags.slice(0, -1));
    }
  }

  function removeTag(tag: string) {
    onChange(tags.filter((t) => t !== tag));
  }

  return (
    <div
      className={cn(
        "flex flex-wrap gap-1.5 px-3 py-2 min-h-[42px] rounded-xl border border-input bg-card focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20 transition-colors",
        className
      )}
      onClick={(e) => (e.currentTarget.querySelector("input") as HTMLInputElement | null)?.focus()}
    >
      {tags.map((tag) => (
        <span
          key={tag}
          className="inline-flex items-center gap-0.5 ps-2.5 pe-0.5 py-1 rounded-full bg-primary/10 text-primary text-xs font-medium"
        >
          {tag}
          <button
            type="button"
            aria-label={`Remove ${tag}`}
            onClick={(e) => { e.stopPropagation(); removeTag(tag); }}
            className="grid size-6 place-items-center rounded-full hover:bg-primary/10 hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
          >
            <X size={12} />
          </button>
        </span>
      ))}
      <input
        id={id}
        aria-describedby={describedBy}
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKey}
        onBlur={() => addTag(input)}
        placeholder={tags.length === 0 ? placeholder : ""}
        className="flex-1 min-w-20 text-sm outline-none bg-transparent placeholder:text-muted-foreground"
      />
    </div>
  );
}
