"use client";

import { Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { FILTER_CONTROL, FILTER_LABEL } from "@/lib/filter-field-classes";

interface SearchInputProps {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  label?: string;
  id?: string;
  className?: string;
}

/** Standardized search field. Debouncing stays in the page (via useDebounce). */
export function SearchInput({
  value,
  onChange,
  placeholder = "Search…",
  label = "Search",
  id = "search",
  className,
}: SearchInputProps) {
  return (
    <div className={cn("min-w-0", className)}>
      <label htmlFor={id} className={FILTER_LABEL}>{label}</label>
      <div className="relative">
        <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          id={id}
          type="search"
          autoComplete="off"
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={cn(FILTER_CONTROL, "pl-9")}
        />
      </div>
    </div>
  );
}
