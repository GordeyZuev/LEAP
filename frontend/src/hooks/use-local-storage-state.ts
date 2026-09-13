"use client";

import { useCallback, useSyncExternalStore } from "react";

const listeners = new Map<string, Set<() => void>>();

function subscribeToKey(key: string, onStoreChange: () => void) {
  let bucket = listeners.get(key);
  if (!bucket) {
    bucket = new Set();
    listeners.set(key, bucket);
  }
  bucket.add(onStoreChange);
  const onStorage = (event: StorageEvent) => {
    if (event.key === key || event.key === null) onStoreChange();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    bucket.delete(onStoreChange);
    if (bucket.size === 0) listeners.delete(key);
    window.removeEventListener("storage", onStorage);
  };
}

function emit(key: string) {
  listeners.get(key)?.forEach((fn) => fn());
}

/**
 * Persist a value in localStorage. SSR / first paint uses `fallback`; the client
 * snapshot is read after hydration so the server HTML stays stable.
 */
export function useLocalStorageState<T>(
  key: string,
  fallback: T,
  parse: (raw: string | null) => T | undefined,
  serialize: (value: T) => string = String,
): [T, (next: T) => void] {
  const subscribe = useCallback(
    (onStoreChange: () => void) => subscribeToKey(key, onStoreChange),
    [key],
  );

  const getSnapshot = () => {
    const parsed = parse(localStorage.getItem(key));
    return parsed === undefined ? fallback : parsed;
  };

  const value = useSyncExternalStore(subscribe, getSnapshot, () => fallback);

  const setValue = useCallback(
    (next: T) => {
      localStorage.setItem(key, serialize(next));
      emit(key);
    },
    [key, serialize],
  );

  return [value, setValue];
}
