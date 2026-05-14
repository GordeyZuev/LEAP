"use client";

import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Play, CheckCircle2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/api/client";

interface AutomationJob {
  id: number;
  name: string;
  description?: string | null;
  is_active: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
  run_count: number;
}

interface AutomationJobListResponse {
  items: AutomationJob[];
  total: number;
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const isCurrentYear = d.getFullYear() === new Date().getFullYear();
  return d.toLocaleString("ru-RU", {
    day: "numeric",
    month: "short",
    ...(isCurrentYear ? {} : { year: "numeric" }),
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function AutomationPage() {
  const qc = useQueryClient();

  const { data, isLoading, error } = useQuery<AutomationJobListResponse>({
    queryKey: ["automation-jobs"],
    queryFn: async () => {
      const res = await apiClient.get<AutomationJobListResponse>("/automation/jobs?per_page=50");
      return res.data;
    },
  });

  const runNow = useMutation({
    mutationFn: (id: number) => apiClient.post(`/automation/jobs/${id}/run`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["automation-jobs"] }),
  });

  const jobs = data?.items ?? [];

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Автоматизации</h1>
        <Link
          href="/automation/new"
          className="flex items-center gap-2 bg-[#224C87] text-white px-4 py-2 rounded-xl text-sm font-medium hover:bg-[#1a3d6e] transition-colors"
        >
          <Plus size={16} /> Новая задача
        </Link>
      </div>

      <div className="bg-white rounded-2xl border border-[#D9D9D9] shadow-sm overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-[#D9D9D9]">
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Задача</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Последний запуск</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Следующий запуск</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Запусков</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Статус</th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wide">Действия</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#D9D9D9]">
            {isLoading && (
              <tr>
                <td colSpan={6} className="px-6 py-12 text-center text-sm text-gray-400">
                  Загрузка…
                </td>
              </tr>
            )}
            {error && (
              <tr>
                <td colSpan={6} className="px-6 py-12 text-center text-sm text-red-400">
                  Не удалось загрузить задачи
                </td>
              </tr>
            )}
            {!isLoading && !error && jobs.length === 0 && (
              <tr>
                <td colSpan={6} className="px-6 py-12 text-center text-sm text-gray-400">
                  Нет задач автоматизации.{" "}
                  <Link href="/automation/new" className="text-[#224C87] hover:underline">
                    Создать первую →
                  </Link>
                </td>
              </tr>
            )}
            {jobs.map((job) => (
              <tr key={job.id} className="hover:bg-gray-50 transition-colors">
                <td className="px-6 py-4">
                  <Link
                    href={`/automation/${job.id}`}
                    className="text-sm font-medium text-gray-900 hover:text-[#224C87] transition-colors"
                  >
                    {job.name}
                  </Link>
                  {job.description && (
                    <p className="text-xs text-gray-400 mt-0.5 truncate max-w-xs">{job.description}</p>
                  )}
                </td>
                <td className="px-6 py-4 text-sm text-gray-500">{formatDate(job.last_run_at)}</td>
                <td className="px-6 py-4 text-sm text-gray-700 font-medium">{formatDate(job.next_run_at)}</td>
                <td className="px-6 py-4 text-sm text-gray-500">{job.run_count}</td>
                <td className="px-6 py-4">
                  <span
                    className={cn(
                      "inline-flex items-center gap-1.5 text-sm",
                      job.is_active ? "text-green-600" : "text-gray-400"
                    )}
                  >
                    {job.is_active ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
                    {job.is_active ? "Активна" : "Неактивна"}
                  </span>
                </td>
                <td className="px-6 py-4">
                  <button
                    onClick={() => runNow.mutate(job.id)}
                    disabled={runNow.isPending}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border border-[#D9D9D9] bg-white hover:bg-[#224C87] hover:text-white hover:border-[#224C87] disabled:opacity-40 transition-colors"
                  >
                    <Play size={12} /> Запустить
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
