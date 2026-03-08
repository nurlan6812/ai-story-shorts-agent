"use client";

import { useEffect, useState, useCallback } from "react";
import { apiFetch } from "@/lib/api";

interface UseApiOptions {
  interval?: number; // 폴링 간격 (ms), 기본 5000
  enabled?: boolean;
}

export function useApi<T>(path: string, options: UseApiOptions = {}) {
  const { interval = 5000, enabled = true } = options;
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!enabled) return;
    try {
      const result = await apiFetch<T>(path);
      setData(result);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "API 연결 실패");
    } finally {
      setLoading(false);
    }
  }, [path, enabled]);

  useEffect(() => {
    fetchData();
    const timer = setInterval(fetchData, interval);
    return () => clearInterval(timer);
  }, [fetchData, interval]);

  return { data, loading, error, refetch: fetchData };
}
