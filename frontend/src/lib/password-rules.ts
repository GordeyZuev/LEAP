/**
 * Password policy shown to the user.
 *
 * Mirrors what the API enforces, and is shared by every screen that sets a
 * password so the rules cannot drift between sign-up and reset.
 */
export interface PasswordRule {
  id: string;
  label: string;
  test: (password: string) => boolean;
}

export const PASSWORD_RULES: PasswordRule[] = [
  { id: "len", label: "At least 8 characters", test: (pw) => pw.length >= 8 },
  { id: "digit", label: "Contains a digit", test: (pw) => /\d/.test(pw) },
  { id: "upper", label: "Contains an uppercase letter", test: (pw) => /[A-Z]/.test(pw) },
];

export function firstFailedRule(password: string): PasswordRule | null {
  return PASSWORD_RULES.find((rule) => !rule.test(password)) ?? null;
}

export function isPasswordValid(password: string): boolean {
  return PASSWORD_RULES.every((rule) => rule.test(password));
}
