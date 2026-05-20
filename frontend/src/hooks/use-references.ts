import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";

interface ReferenceItem {
  value: string;
  label: string;
}

const QUERY_OPTIONS = {
  staleTime: Infinity,
  gcTime: 24 * 60 * 60 * 1000,
} as const;

async function fetchReference(path: string): Promise<ReferenceItem[]> {
  const { data } = await apiClient.get<ReferenceItem[]>(`/references/${path}`);
  return data;
}

export function useLanguages() {
  return useQuery({
    queryKey: ["references", "languages"],
    queryFn: () => fetchReference("languages"),
    ...QUERY_OPTIONS,
  });
}

export function useGranularities() {
  return useQuery({
    queryKey: ["references", "granularities"],
    queryFn: () => fetchReference("granularities"),
    ...QUERY_OPTIONS,
  });
}

export function useQualities() {
  return useQuery({
    queryKey: ["references", "qualities"],
    queryFn: () => fetchReference("qualities"),
    ...QUERY_OPTIONS,
  });
}

export function usePlatforms() {
  return useQuery({
    queryKey: ["references", "platforms"],
    queryFn: () => fetchReference("platforms"),
    ...QUERY_OPTIONS,
  });
}

export function useTimezones() {
  return useQuery({
    queryKey: ["references", "timezones"],
    queryFn: () => fetchReference("timezones"),
    ...QUERY_OPTIONS,
  });
}
