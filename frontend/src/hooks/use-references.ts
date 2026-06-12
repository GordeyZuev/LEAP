import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type { DisplayConfigDefaultsPayload } from "@/lib/display-config-defaults";
import { DISPLAY_CONFIG_PLACEHOLDER } from "@/lib/display-config-defaults";

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

export function useDisplayConfigDefaults() {
  return useQuery({
    queryKey: ["references", "display-config-defaults"],
    queryFn: async () => {
      const { data } = await apiClient.get<DisplayConfigDefaultsPayload>(
        "/references/display-config-defaults",
      );
      return data;
    },
    placeholderData: DISPLAY_CONFIG_PLACEHOLDER,
    ...QUERY_OPTIONS,
  });
}
