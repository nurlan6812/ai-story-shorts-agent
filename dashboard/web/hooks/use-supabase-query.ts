"use client";

import { useEffect, useState, useCallback } from "react";
import { supabase } from "@/lib/supabase";

interface UseSupabaseQueryOptions<T> {
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
}: UseSupabaseQueryOptions<T>) {
  const [data, setData] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      let query = supabase.from(table).select(select);

      if (filter) {
        query = query.eq(filter.column, filter.value);
      }
      if (order) {
        query = query.order(order.column, {
          ascending: order.ascending ?? false,
        });
      }
      if (limit) {
        query = query.limit(limit);
      }

      const { data: result, error: err } = await query;

      if (err) {
        setError(err.message);
      } else {
        setData((result as T[]) ?? []);
        setError(null);
      }
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
