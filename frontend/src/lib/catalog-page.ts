export const CATALOG_PAGE_SIZE = 24;

export function parseCatalogPage(raw: string | null): number {
  const n = Number(raw);
  return Number.isInteger(n) && n >= 1 ? n : 1;
}

export function paginateItems<T>(items: T[], page: number, perPage = CATALOG_PAGE_SIZE) {
  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / perPage) || 1);
  const safe = Math.min(Math.max(1, page), totalPages);
  const start = (safe - 1) * perPage;
  return { page: safe, totalPages, total, items: items.slice(start, start + perPage) };
}
