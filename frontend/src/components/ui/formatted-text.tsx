"use client";

import { useLayoutEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";
import { parseFormattedText, type FormattedNode } from "@/lib/formatted-text";

function Nodes({ nodes }: { nodes: FormattedNode[] }) {
  return nodes.map((n, i) => {
    if (n.type === "text") return <span key={i}>{n.value}</span>;
    if (n.type === "jinja") {
      return (
        <code key={i} className="rounded-sm bg-muted px-0.5 font-mono text-[0.9em] text-primary">
          {n.value}
        </code>
      );
    }
    if (n.type === "strong") {
      return (
        <strong key={i} className="font-semibold text-foreground">
          <Nodes nodes={n.children} />
        </strong>
      );
    }
    if (n.type === "em") {
      return (
        <em key={i}>
          <Nodes nodes={n.children} />
        </em>
      );
    }
    if (n.type === "underline") {
      return (
        <u key={i}>
          <Nodes nodes={n.children} />
        </u>
      );
    }
    if (n.type === "strike") {
      return (
        <s key={i}>
          <Nodes nodes={n.children} />
        </s>
      );
    }
    return (
      <a
        key={i}
        href={n.href}
        target="_blank"
        rel="noopener noreferrer"
        className="font-medium text-primary underline-offset-2 hover:underline"
      >
        <Nodes nodes={n.children} />
      </a>
    );
  });
}

export function FormattedText({
  text,
  className,
}: {
  text: string;
  className?: string;
}) {
  return (
    <p className={cn("whitespace-pre-wrap break-words", className)}>
      <Nodes nodes={parseFormattedText(text)} />
    </p>
  );
}

const COLLAPSED_MAX = "max-h-[6.5em]";

/** Full-width formatted blurb; overflow fades into the page, then Show more. */
export function ExpandableFormattedText({
  text,
  className,
}: {
  text: string;
  className?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const [overflows, setOverflows] = useState(false);
  const ref = useRef<HTMLParagraphElement>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    function measure() {
      if (!el || expanded) return;
      setOverflows(el.scrollHeight > el.clientHeight + 1);
    }
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [text, expanded]);

  const collapsedOverflow = overflows || expanded;

  return (
    <div className={cn("w-full", className)}>
      <div className="relative">
        <p
          ref={ref}
          className={cn(
            "whitespace-pre-wrap break-words text-sm leading-relaxed text-muted-foreground",
            !expanded && cn(COLLAPSED_MAX, "overflow-hidden"),
          )}
        >
          <Nodes nodes={parseFormattedText(text)} />
        </p>
        {collapsedOverflow && !expanded ? (
          <div
            className="pointer-events-none absolute inset-x-0 bottom-0 h-4 bg-gradient-to-t from-background/40 to-transparent"
            aria-hidden
          />
        ) : null}
      </div>
      {collapsedOverflow && !expanded ? (
        <button
          type="button"
          aria-expanded={false}
          onClick={() => setExpanded(true)}
          className="mt-1 inline-flex min-h-9 items-center rounded-sm text-sm font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
        >
          Show more
        </button>
      ) : null}
      {expanded ? (
        <button
          type="button"
          aria-expanded
          onClick={() => setExpanded(false)}
          className="mt-2 inline-flex min-h-9 items-center rounded-sm text-sm font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
        >
          Show less
        </button>
      ) : null}
    </div>
  );
}
