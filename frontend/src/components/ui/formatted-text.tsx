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
