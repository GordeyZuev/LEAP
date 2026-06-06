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
}

function childrenToOptions(children: ReactNode): FilterSelectOption[] {
  const opts: FilterSelectOption[] = [];
  Children.forEach(children, (child) => {
    if (!isValidElement(child) || child.type !== "option") return;
    const props = child.props as { value?: string | number; children?: ReactNode };
    const label =
      typeof props.children === "string" ? props.children : String(props.children ?? "");
    opts.push({ value: String(props.value ?? ""), label });
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
}: NativeSelectProps) {
  const options = childrenToOptions(children);
  return (
    <FilterSelect
      value={String(value ?? "")}
      options={options}
      disabled={disabled}
      className={cn(wrapperClassName, className)}
      onChange={(v) =>
        // Synthesize the minimal change event shape that call sites read.
        onChange?.({ target: { value: v } } as unknown as React.ChangeEvent<HTMLSelectElement>)
      }
    />
  );
}
