"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Clock, Circle } from "lucide-react";
import { formatDistanceToNow, parseISO } from "date-fns";
import { ko } from "date-fns/locale";
import type { SchedulerOverview, SchedulerStatus } from "@/lib/types";

function SchedulerRow({ scheduler }: { scheduler: SchedulerStatus }) {
  const [countdown, setCountdown] = useState("");

  useEffect(() => {
    if (!scheduler?.next_run) return;

    function update() {
      if (!scheduler?.next_run) return;
      const dist = formatDistanceToNow(parseISO(scheduler.next_run), {
        locale: ko,
        addSuffix: true,
      });
      setCountdown(dist);
    }

    update();
    const timer = setInterval(update, 30000);
    return () => clearInterval(timer);
  }, [scheduler?.next_run]);

  return (
    <div className="rounded-lg border border-border bg-[#0a0a0a] px-3 py-2.5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className={scheduler.running ? "pulse-green rounded-full" : ""}>
            <Circle
              className={`h-3 w-3 fill-current ${
                scheduler.running ? "text-emerald-400" : "text-red-400"
              }`}
            />
          </div>
          <div>
            <p className="text-sm font-medium">{scheduler.label}</p>
            <p className="text-[11px] text-muted-foreground">
              {scheduler.running ? "실행중" : "정지"}
              {scheduler.pid ? ` · PID ${scheduler.pid}` : ""}
            </p>
          </div>
        </div>
        <span className="text-[11px] text-muted-foreground">
          {scheduler.next_run ? countdown : "예정 없음"}
        </span>
      </div>
    </div>
  );
}

export function SchedulerStatusCard({
  scheduler,
}: {
  scheduler: SchedulerOverview | null;
}) {
  const main = scheduler?.main;
  const recovery = scheduler?.recovery;

  return (
    <Card className="glow-border">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          스케줄러
        </CardTitle>
        <Clock className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        {main && recovery ? (
          <div className="space-y-2">
            <SchedulerRow scheduler={main} />
            <SchedulerRow scheduler={recovery} />
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            스케줄러 상태를 불러오는 중입니다.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
