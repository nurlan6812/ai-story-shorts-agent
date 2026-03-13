"use client";

import { useEffect, useState, useCallback } from "react";
import { apiFetch } from "@/lib/api";

interface UseSupabaseQueryOptions {
  table: string;
  select?: string;
  order?: { column: string; ascending?: boolean };
  filter?: { column: string; value: string };
  limit?: number;
  interval?: number; // 폴링 간격 (ms), 기본 10000
}

export function useSupabaseQuery<T>({
  table,
  select = "*",
  order,
  filter,
  limit,
  interval = 10000,
}: UseSupabaseQueryOptions) {
  const [data, setData] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const params = new URLSearchParams({
        table,
        select,
      });

      if (filter) {
        params.set("filter_column", filter.column);
        params.set("filter_value", filter.value);
      }
      if (order) {
        params.set("order_column", order.column);
        params.set("ascending", String(order.ascending ?? false));
      }
      if (limit) {
        params.set("limit", String(limit));
      }

      const result = await apiFetch<{ data: T[] }>(
        `/api/data/query?${params.toString()}`
      );
      setData(result.data ?? []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "알 수 없는 오류");
    } finally {
      setLoading(false);
    }
  }, [table, select, order?.column, order?.ascending, filter?.column, filter?.value, limit]);

  useEffect(() => {
    fetchData();
    const timer = setInterval(fetchData, interval);
    return () => clearInterval(timer);
  }, [fetchData, interval]);

  return { data, loading, error, refetch: fetchData };
}
