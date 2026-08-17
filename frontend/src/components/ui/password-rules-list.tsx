"use client";

import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { PASSWORD_RULES } from "@/lib/password-rules";

interface PasswordRulesListProps {
  password: string;
  /** Show unmet rules in red once the field has been visited or typed into. */
  showErrors?: boolean;
  id?: string;
}

/** Live checklist of the password policy — used on sign-up and password reset. */
export function PasswordRulesList({ password, showErrors = false, id }: PasswordRulesListProps) {
  return (
    <ul id={id} className="mt-2 space-y-1">
      {PASSWORD_RULES.map((rule) => {
        const ok = rule.test(password);
        const failed = (showErrors || password.length > 0) && !ok;
        return (
          <li
            key={rule.id}
            className={cn(
              "flex items-center gap-1.5 text-[11px] transition-colors",
              ok ? "text-success-fg" : failed ? "text-danger-fg" : "text-muted-foreground",
            )}
          >
            <Check size={11} className={cn("shrink-0 transition-opacity", ok ? "opacity-100" : "opacity-30")} />
            {rule.label}
          </li>
        );
      })}
    </ul>
  );
}
