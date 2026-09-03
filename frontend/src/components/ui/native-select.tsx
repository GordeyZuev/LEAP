"use client";

import { Children, isValidElement, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { FilterSelect, type FilterSelectOption } from "@/components/filters/filter-select";

// NativeSelect keeps the familiar <select>-style API (value + onChange event +
// <option> children) but renders the unified custom popover (FilterSelect) so
// every selector in the app looks identical. Drop-in: existing call sites that
// read e.target.value keep working.
interface NativeSelectProps {
  value: string | number;
  onChange?: React.ChangeEventHandler<HTMLSelectElement>;
  children: ReactNode;
  className?: string;
  wrapperClassName?: string;
  disabled?: boolean;
  /** Forwarded to the trigger so an external <label htmlFor> resolves. */
  id?: string;
  "aria-describedby"?: string;
  ariaLabel?: string;
}

/** Join an option's text parts: `<option>{q}p</option>` arrives as an array of
 *  children, and stringifying that array would render "720,p". */
function optionLabel(children: ReactNode): string {
  return Children.toArray(children)
    .map((part) => (typeof part === "string" || typeof part === "number" ? String(part) : ""))
    .join("");
}

function childrenToOptions(children: ReactNode): FilterSelectOption[] {
  const opts: FilterSelectOption[] = [];
  Children.forEach(children, (child) => {
    if (!isValidElement(child) || child.type !== "option") return;
    const props = child.props as { value?: string | number; children?: ReactNode };
    opts.push({ value: String(props.value ?? ""), label: optionLabel(props.children) });
  });
  return opts;
}

export function NativeSelect({
  value,
  onChange,
  children,
  className,
  wrapperClassName,
  disabled,
  id,
  "aria-describedby": describedBy,
  ariaLabel,
}: NativeSelectProps) {
  const options = childrenToOptions(children);
  return (
    <FilterSelect
      value={String(value ?? "")}
      options={options}
      disabled={disabled}
      id={id}
      aria-describedby={describedBy}
      ariaLabel={ariaLabel}
      className={cn(wrapperClassName, className)}
      onChange={(v) =>
        // Synthesize the minimal change event shape that call sites read.
        onChange?.({ target: { value: v } } as unknown as React.ChangeEvent<HTMLSelectElement>)
      }
    />
  );
}
