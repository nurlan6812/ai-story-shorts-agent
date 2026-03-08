"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Clock, Circle } from "lucide-react";
import { formatDistanceToNow, parseISO } from "date-fns";
import { ko } from "date-fns/locale";
import type { SchedulerStatus } from "@/lib/types";

export function SchedulerStatusCard({
  scheduler,
}: {
  scheduler: SchedulerStatus | null;
}) {
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
    <Card className="glow-border">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          스케줄러
        </CardTitle>
        <Clock className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="flex items-center gap-2">
          <div className={scheduler?.running ? "pulse-green rounded-full" : ""}>
            <Circle
              className={`h-3 w-3 fill-current ${
                scheduler?.running ? "text-emerald-400" : "text-red-400"
              }`}
            />
          </div>
          <span className="text-2xl font-bold">
            {scheduler?.running ? "실행중" : "정지"}
          </span>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          {scheduler?.next_run ? (
            <>다음 실행: {countdown}</>
          ) : (
            "예정된 실행 없음"
          )}
          {scheduler?.pid && (
            <span className="ml-2 text-[10px]">PID: {scheduler.pid}</span>
          )}
        </p>
      </CardContent>
    </Card>
  );
}
