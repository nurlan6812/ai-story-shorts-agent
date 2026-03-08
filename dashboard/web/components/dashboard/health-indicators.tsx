"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Activity, CheckCircle2, XCircle } from "lucide-react";
import type { HealthStatus } from "@/lib/types";

function HealthItem({
  label,
  ok,
  detail,
}: {
  label: string;
  ok: boolean;
  detail?: string;
}) {
  return (
    <div className="flex items-center justify-between py-1">
      <div className="flex items-center gap-2">
        {ok ? (
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
        ) : (
          <XCircle className="h-3.5 w-3.5 text-red-400" />
        )}
        <span className="text-sm">{label}</span>
      </div>
      {detail && (
        <span className="text-xs text-muted-foreground">{detail}</span>
      )}
    </div>
  );
}

export function HealthIndicators({
  health,
}: {
  health: HealthStatus | null;
}) {
  if (!health) return null;

  return (
    <Card className="glow-border">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          시스템 헬스
        </CardTitle>
        <Activity className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent className="space-y-1">
        <HealthItem label="YouTube 토큰" ok={health.youtube_token} />
        <HealthItem label="Supabase" ok={health.supabase} />
        <HealthItem
          label="디스크"
          ok={health.disk_free_gb > 5}
          detail={`${health.disk_free_gb} GB`}
        />
        <HealthItem
          label="쿼터"
          ok={health.quota.can_upload}
          detail={`${health.quota.remaining}회 남음`}
        />
      </CardContent>
    </Card>
  );
}
