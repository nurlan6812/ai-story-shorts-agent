"use client";

import { CircleOff, RotateCcw, ShieldAlert, ShieldCheck, TriangleAlert } from "lucide-react";

import { useApi } from "@/hooks/use-api";
import type { RecoveryActivityResponse } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const statusMeta = {
  verified: {
    label: "결과 확인",
    icon: ShieldCheck,
    className: "text-emerald-400 border-emerald-500/30",
  },
  retry_triggered: {
    label: "보강 재시도",
    icon: RotateCcw,
    className: "text-amber-400 border-amber-500/30",
  },
  completed: {
    label: "복구 완료",
    icon: ShieldCheck,
    className: "text-blue-400 border-blue-500/30",
  },
  failed: {
    label: "복구 실패",
    icon: TriangleAlert,
    className: "text-red-400 border-red-500/30",
  },
  skipped: {
    label: "조회 불가",
    icon: CircleOff,
    className: "text-muted-foreground border-border",
  },
  info: {
    label: "기타",
    icon: ShieldAlert,
    className: "text-muted-foreground border-border",
  },
} as const;

export function RecoveryActivity() {
  const { data } = useApi<RecoveryActivityResponse>(
    "/api/scheduler/recovery-activity?limit=8",
    { interval: 5000 }
  );

  const activities = data?.activities ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">
          복구 스케줄러 최근 활동
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          슬롯 점검, 누락 감지, 보강 업로드 이력을 최근순으로 표시합니다.
        </p>
      </CardHeader>
      <CardContent>
        {activities.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            최근 복구 활동이 없습니다
          </p>
        ) : (
          <div className="space-y-2">
            {activities.map((activity, index) => {
              const meta = statusMeta[activity.status] ?? statusMeta.info;
              const Icon = meta.icon;

              return (
                <div
                  key={`${activity.timestamp}-${activity.slot}-${index}`}
                  className="rounded-lg border border-border bg-[#0a0a0a] px-3 py-2.5"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-muted-foreground">
                          {activity.timestamp}
                        </span>
                        <Badge variant="outline" className={`text-[10px] ${meta.className}`}>
                          <Icon className="mr-1 h-3 w-3" />
                          {meta.label}
                        </Badge>
                      </div>
                      <p className="mt-1 text-sm font-medium">{activity.slot}</p>
                      <p className="mt-1 text-xs text-foreground/75">
                        {activity.title || activity.message}
                      </p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
