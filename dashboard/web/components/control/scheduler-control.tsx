"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { useApi } from "@/hooks/use-api";
import { apiFetch } from "@/lib/api";
import type { SchedulerStatus } from "@/lib/types";
import { Play, Square, Circle } from "lucide-react";
import { formatDistanceToNow, parseISO } from "date-fns";
import { ko } from "date-fns/locale";

export function SchedulerControl() {
  const { data: scheduler, refetch } = useApi<SchedulerStatus>(
    "/api/scheduler/status"
  );
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [message, setMessage] = useState("");

  async function handleAction(action: "start" | "stop") {
    setLoading(true);
    setMessage("");
    try {
      await apiFetch(`/api/scheduler/${action}`, { method: "POST" });
      setMessage(
        action === "start"
          ? "스케줄러가 시작되었습니다"
          : "스케줄러가 정지되었습니다"
      );
      setTimeout(refetch, 1000);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "오류 발생");
    } finally {
      setLoading(false);
      setDialogOpen(false);
    }
  }

  const nextRunLabel = scheduler?.next_run
    ? formatDistanceToNow(parseISO(scheduler.next_run), {
        locale: ko,
        addSuffix: true,
      })
    : null;

  return (
    <Card className={scheduler?.running ? "glow-border" : ""}>
      <CardHeader>
        <CardTitle className="text-sm font-medium">스케줄러 제어</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-3">
          <div className={scheduler?.running ? "pulse-green rounded-full" : ""}>
            <Circle
              className={`h-4 w-4 fill-current ${
                scheduler?.running ? "text-emerald-400" : "text-red-400"
              }`}
            />
          </div>
          <div>
            <p className="text-sm font-medium">
              {scheduler?.running ? "실행중" : "정지됨"}
            </p>
            {scheduler?.pid && (
              <p className="text-xs text-muted-foreground">
                PID: {scheduler.pid}
              </p>
            )}
          </div>
        </div>

        {nextRunLabel && (
          <p className="text-xs text-muted-foreground">
            다음 실행: {nextRunLabel}
          </p>
        )}

        <div className="flex gap-2">
          {scheduler?.running ? (
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button variant="destructive" size="sm" className="gap-1.5">
                  <Square className="h-3 w-3" /> 정지
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>스케줄러 정지</DialogTitle>
                  <DialogDescription>
                    스케줄러를 정지하면 자동 영상 생성이 중단됩니다.
                    계속하시겠습니까?
                  </DialogDescription>
                </DialogHeader>
                <DialogFooter>
                  <Button
                    variant="outline"
                    onClick={() => setDialogOpen(false)}
                  >
                    취소
                  </Button>
                  <Button
                    variant="destructive"
                    onClick={() => handleAction("stop")}
                    disabled={loading}
                  >
                    {loading ? "정지 중..." : "정지"}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          ) : (
            <Button
              size="sm"
              className="gap-1.5"
              onClick={() => handleAction("start")}
              disabled={loading}
            >
              <Play className="h-3 w-3" /> {loading ? "시작 중..." : "시작"}
            </Button>
          )}
        </div>

        {message && <p className="text-xs text-blue-400">{message}</p>}
      </CardContent>
    </Card>
  );
}
