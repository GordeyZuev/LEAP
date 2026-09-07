export function templateHasJinjaVar(text: string, varName: string): boolean {
  const re = new RegExp(`\\{\\{[-+\\s]*${varName}\\b`);
  return re.test(text);
}

export function combinedHasJinjaVar(varName: string, ...parts: Array<string | undefined | null>): boolean {
  return parts.some((p) => p != null && templateHasJinjaVar(p, varName));
}
