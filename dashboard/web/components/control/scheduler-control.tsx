"use client";

import { useState } from "react";
import { format, formatDistanceToNow, parseISO } from "date-fns";
import { ko } from "date-fns/locale";
import { Circle, Clock3, FileText, Play, Square } from "lucide-react";

import { useApi } from "@/hooks/use-api";
import { apiFetch } from "@/lib/api";
import type { SchedulerStatus, SchedulerTarget } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

const confirmText: Record<SchedulerTarget, string> = {
  main: "메인 스케줄러를 정지하면 정규 자동 영상 생성이 중단됩니다.",
  recovery: "복구 스케줄러를 정지하면 누락 슬롯 보강 재시도가 중단됩니다.",
};

interface SchedulerControlProps {
  target: SchedulerTarget;
  title: string;
  description: string;
}

export function SchedulerControl({
  target,
  title,
  description,
}: SchedulerControlProps) {
  const { data: scheduler, error, refetch } = useApi<SchedulerStatus>(
    `/api/scheduler/status/${target}`
  );
  const [actionLoading, setActionLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [message, setMessage] = useState("");

  async function handleAction(action: "start" | "stop") {
    setActionLoading(true);
    setMessage("");
    try {
      await apiFetch(`/api/scheduler/${action}/${target}`, { method: "POST" });
      setMessage(
        action === "start"
          ? `${title}가 시작되었습니다`
          : `${title}가 정지되었습니다`
      );
      setTimeout(refetch, 1000);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "오류 발생");
    } finally {
      setActionLoading(false);
      setDialogOpen(false);
    }
  }

  const nextRunLabel = scheduler?.next_run
    ? formatDistanceToNow(parseISO(scheduler.next_run), {
        locale: ko,
        addSuffix: true,
      })
    : null;
  const lastLogLabel = scheduler?.last_log_at
    ? format(parseISO(scheduler.last_log_at.replace(" ", "T")), "MM/dd HH:mm:ss", {
        locale: ko,
      })
    : null;

  return (
    <Card className={scheduler?.running ? "glow-border" : ""}>
      <CardHeader>
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <p className="text-xs text-muted-foreground">{description}</p>
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
              {scheduler
                ? scheduler.running
                  ? "실행중"
                  : "정지됨"
                : error
                  ? "연결 실패"
                  : "불러오는 중"}
            </p>
            {scheduler?.pid && scheduler.pids.length > 0 && (
              <p className="text-xs text-muted-foreground">
                PID: {scheduler.pid}
                {scheduler.pids.length > 1
                  ? ` 외 ${scheduler.pids.length - 1}`
                  : ""}
              </p>
            )}
          </div>
        </div>

        <div className="space-y-1.5 rounded-lg border border-border bg-[#0a0a0a] p-3">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Clock3 className="h-3.5 w-3.5" />
            {scheduler
              ? nextRunLabel
                ? `다음 실행: ${nextRunLabel}`
                : "다음 실행 없음"
              : "상태 조회 불가"}
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <FileText className="h-3.5 w-3.5" />
            최근 로그: {scheduler ? lastLogLabel ?? "없음" : "조회 실패"}
          </div>
        </div>

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
                  <DialogTitle>{title} 정지</DialogTitle>
                  <DialogDescription>
                    {confirmText[target]} 계속하시겠습니까?
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
                    disabled={actionLoading}
                  >
                    {actionLoading ? "정지 중..." : "정지"}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          ) : (
            <Button
              size="sm"
              className="gap-1.5"
              onClick={() => handleAction("start")}
              disabled={actionLoading}
            >
              <Play className="h-3 w-3" /> {actionLoading ? "시작 중..." : "시작"}
            </Button>
          )}
        </div>

        {error && <p className="text-xs text-red-400">{error}</p>}
        {message && <p className="text-xs text-blue-400">{message}</p>}
      </CardContent>
    </Card>
  );
}
