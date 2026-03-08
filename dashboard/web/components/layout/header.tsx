"use client";

import { useApi } from "@/hooks/use-api";
import type { SchedulerStatus, HealthStatus } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Circle } from "lucide-react";

export function Header() {
  const { data: scheduler } = useApi<SchedulerStatus>("/api/scheduler/status");
  const { data: health } = useApi<HealthStatus>("/api/health/status", {
    interval: 30000,
  });

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-border bg-card/80 px-6 backdrop-blur">
      <div />
      <div className="flex items-center gap-4">
        {/* 스케줄러 상태 */}
        <div className="flex items-center gap-2">
          <Circle
            className={`h-2 w-2 fill-current ${
              scheduler?.running ? "text-emerald-400" : "text-red-400"
            }`}
          />
          <span className="text-xs text-muted-foreground">
            스케줄러 {scheduler?.running ? "실행중" : "정지"}
          </span>
        </div>

        {/* 헬스 배지들 */}
        {health && (
          <div className="flex items-center gap-2">
            <Badge
              variant={health.youtube_token ? "default" : "destructive"}
              className="text-[10px] px-1.5 py-0"
            >
              YT {health.youtube_token ? "OK" : "만료"}
            </Badge>
            <Badge
              variant={health.supabase ? "default" : "destructive"}
              className="text-[10px] px-1.5 py-0"
            >
              DB {health.supabase ? "OK" : "오류"}
            </Badge>
            <Badge variant="outline" className="text-[10px] px-1.5 py-0">
              {health.quota.used}/{health.quota.limit}
            </Badge>
          </div>
        )}
      </div>
    </header>
  );
}
