"use client";

import { useApi } from "@/hooks/use-api";
import type { SchedulerOverview, HealthStatus } from "@/lib/types";
import { QuotaCard } from "@/components/dashboard/quota-card";
import { SchedulerStatusCard } from "@/components/dashboard/scheduler-status";
import { RecentVideos } from "@/components/dashboard/recent-videos";
import { ErrorSummary } from "@/components/dashboard/error-summary";
import { HealthIndicators } from "@/components/dashboard/health-indicators";

export default function DashboardPage() {
  const { data: scheduler } = useApi<SchedulerOverview>("/api/scheduler/status");
  const { data: health } = useApi<HealthStatus>("/api/health/status", {
    interval: 30000,
  });

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-display">대시보드</h1>

      {/* 상단 카드 행 */}
      <div className="grid grid-cols-4 gap-4">
        <QuotaCard health={health} />
        <SchedulerStatusCard scheduler={scheduler} />
        <ErrorSummary />
        <HealthIndicators health={health} />
      </div>

      {/* 하단 영역 */}
      <div className="grid grid-cols-2 gap-4">
        <RecentVideos />
      </div>
    </div>
  );
}
