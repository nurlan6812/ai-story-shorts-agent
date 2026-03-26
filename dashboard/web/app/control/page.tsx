"use client";

import { useState } from "react";
import { SchedulerControl } from "@/components/control/scheduler-control";
import { RecoveryActivity } from "@/components/control/recovery-activity";
import { ManualGenerate } from "@/components/control/manual-generate";
import { PatternManager } from "@/components/control/pattern-manager";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import { LogViewer } from "@/components/logs/log-viewer";
import { Terminal, Maximize2, Minimize2 } from "lucide-react";
import type { LogTarget, LogsResponse } from "@/lib/types";

const levels = ["DEBUG", "INFO", "WARNING", "ERROR"];
const logTargets = [
  { label: "전체", value: "all" },
  { label: "메인", value: "main" },
  { label: "복구", value: "recovery" },
] as const;

export default function ControlPage() {
  const [level, setLevel] = useState("INFO");
  const [target, setTarget] = useState<LogTarget>("all");
  const [expanded, setExpanded] = useState(false);

  const { data: logData } = useApi<LogsResponse>(
    `/api/logs/tail?lines=${expanded ? 200 : 15}&level=${level}&target=${target}`,
    { interval: 3000 }
  );

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-display">시스템 제어</h1>

      <div className="grid gap-4 lg:grid-cols-3">
        <SchedulerControl
          target="main"
          title="메인 스케줄러"
          description="정규 슬롯 06:30, 11:30, 18:30에 영상 생성과 업로드를 담당합니다."
        />
        <SchedulerControl
          target="recovery"
          title="복구 스케줄러"
          description="07:30~09:30, 12:30~14:30, 19:30~21:30에 누락 슬롯을 점검합니다."
        />
        <ManualGenerate />
      </div>

      <RecoveryActivity />

      <PatternManager />

      {/* 실시간 로그 */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between py-2.5 px-4">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Terminal className="h-4 w-4 text-muted-foreground" />
            실시간 로그
            <span className="text-[10px] text-muted-foreground font-normal">
              {logData?.total ?? 0}줄 · 3초 새로고침
            </span>
          </CardTitle>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-0.5 rounded-md bg-muted p-0.5">
              {logTargets.map((item) => (
                <button
                  key={item.value}
                  onClick={() => setTarget(item.value)}
                  className={`px-2 py-0.5 rounded text-[10px] transition-colors ${
                    target === item.value
                      ? "bg-card text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-0.5 rounded-md bg-muted p-0.5">
              {levels.map((l) => (
                <button
                  key={l}
                  onClick={() => setLevel(l)}
                  className={`px-2 py-0.5 rounded text-[10px] transition-colors ${
                    level === l
                      ? "bg-card text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {l}
                </button>
              ))}
            </div>
            <button
              onClick={() => setExpanded(!expanded)}
              className="text-muted-foreground hover:text-foreground transition-colors"
              title={expanded ? "접기" : "전체 보기"}
            >
              {expanded ? (
                <Minimize2 className="h-3.5 w-3.5" />
              ) : (
                <Maximize2 className="h-3.5 w-3.5" />
              )}
            </button>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <LogViewer
            logs={logData?.logs ?? []}
            className={expanded ? "h-[32rem]" : "h-48"}
          />
        </CardContent>
      </Card>
    </div>
  );
}
