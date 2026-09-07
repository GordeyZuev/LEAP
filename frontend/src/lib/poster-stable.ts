/** Fields used to keep poster image URLs stable across list refetches. */
export interface PosterStableFields {
  poster_url?: string | null;
  poster_fallback_url?: string | null;
  poster_asset_key?: string | null;
}

function preservePosterUrls<T extends PosterStableFields>(
  prevItem: T | undefined,
  nextItem: T,
): T {
  if (!prevItem?.poster_asset_key || prevItem.poster_asset_key !== nextItem.poster_asset_key) {
    return nextItem;
  }
  return {
    ...nextItem,
    poster_url: prevItem.poster_url ?? nextItem.poster_url,
    poster_fallback_url: prevItem.poster_fallback_url ?? nextItem.poster_fallback_url,
  };
}

/** Merge poster URLs on refetch when the underlying storage asset is unchanged. */
export function mergePosterFieldsInItems<T extends PosterStableFields & { id: number }>(
  prevItems: T[] | undefined,
  nextItems: T[],
): T[] {
  if (!prevItems?.length) return nextItems;
  const prevById = new Map(prevItems.map((item) => [item.id, item]));
  return nextItems.map((item) => preservePosterUrls(prevById.get(item.id), item));
}

export interface PaginatedWithItems<T> {
  items: T[];
}

/**
 * React Query structuralSharing helper for paginated lists with poster fields.
 */
export function structuralSharingPreservePosters<
  T extends PaginatedWithItems<U>,
  U extends PosterStableFields & { id: number },
>(oldData: T | undefined, newData: T): T {
  if (!oldData) return newData;
  return {
    ...newData,
    items: mergePosterFieldsInItems(oldData.items, newData.items),
  };
}
