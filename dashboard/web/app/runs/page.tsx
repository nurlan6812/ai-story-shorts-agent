"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Line,
  ComposedChart,
} from "recharts";
import { StatusBadge } from "@/components/layout/status-badge";
import { Badge } from "@/components/ui/badge";
import { useSupabaseQuery } from "@/hooks/use-supabase-query";
import { useHasMounted } from "@/hooks/use-has-mounted";
import type { Run } from "@/lib/types";
import {
  format,
  parseISO,
  differenceInSeconds,
  subDays,
  subHours,
  isAfter,
} from "date-fns";
import { ko } from "date-fns/locale";

const typeLabels: Record<string, string> = {
  research: "리서치",
  generate: "영상 생성",
  publish: "업로드",
  collect_analytics: "성과 수집",
  analyze_patterns: "패턴 분석",
};

const triggerLabels: Record<string, string> = {
  manual: "수동",
  schedule: "정규 슬롯",
  slot_check: "복구 점검",
  queue: "대기열",
};

const timeFilters = [
  { label: "24시간", value: "24h" },
  { label: "7일", value: "7d" },
  { label: "30일", value: "30d" },
  { label: "전체", value: "all" },
] as const;

type TimeFilter = (typeof timeFilters)[number]["value"];

function summarizeRunMeta(run: Run) {
  const meta = run.run_meta ?? {};
  const lines: string[] = [];

  const topic = typeof meta.topic === "string" ? meta.topic : null;
  const title = typeof meta.title === "string" ? meta.title : null;
  const uploadTitle =
    typeof meta.upload_title === "string" ? meta.upload_title : null;
  const sourceRegion =
    typeof meta.source_region === "string" ? meta.source_region : null;
  const duplicateCandidate =
    typeof meta.duplicate_candidate === "string"
      ? meta.duplicate_candidate
      : null;
  const seriesTotal =
    typeof meta.series_total === "number" ? meta.series_total : null;

  if (title) lines.push(`제목: ${title}`);
  else if (topic) lines.push(`토픽: ${topic}`);
  if (uploadTitle && uploadTitle !== title) lines.push(`업로드 제목: ${uploadTitle}`);
  if (sourceRegion) lines.push(`소스 지역: ${sourceRegion}`);
  if (seriesTotal && seriesTotal > 1) lines.push(`시리즈 ${seriesTotal}편`);
  if (duplicateCandidate) lines.push(`중복 후보: ${duplicateCandidate.slice(0, 8)}`);

  return lines;
}

export default function RunsPage() {
  const [filter, setFilter] = useState<TimeFilter>("7d");
  const mounted = useHasMounted();

  const { data: runs, loading } = useSupabaseQuery<Run>({
    table: "runs",
    order: { column: "started_at", ascending: false },
    limit: 200,
  });

  // 시간 필터 적용
  const filteredRuns = useMemo(() => {
    if (filter === "all") return runs;
    const now = new Date();
    const cutoff =
      filter === "24h"
        ? subHours(now, 24)
        : filter === "7d"
          ? subDays(now, 7)
          : subDays(now, 30);
    return runs.filter((r) => isAfter(parseISO(r.started_at), cutoff));
  }, [runs, filter]);

  // 일별 실행 횟수 + 에러율
  const dailyData = useMemo(() => {
    const days = new Map<string, { total: number; failed: number }>();
    filteredRuns.forEach((r) => {
      const day = format(parseISO(r.started_at), "MM/dd");
      const prev = days.get(day) || { total: 0, failed: 0 };
      days.set(day, {
        total: prev.total + 1,
        failed: prev.failed + (r.status === "failed" ? 1 : 0),
      });
    });
    return Array.from(days.entries())
      .map(([date, { total, failed }]) => ({
        date,
        total,
        failed,
        errorRate: total > 0 ? Math.round((failed / total) * 100) : 0,
      }))
      .reverse();
  }, [filteredRuns]);

  function formatDuration(run: Run) {
    if (!run.completed_at) return "-";
    const secs = differenceInSeconds(
      parseISO(run.completed_at),
      parseISO(run.started_at)
    );
    if (secs < 60) return `${secs}초`;
    return `${Math.floor(secs / 60)}분 ${secs % 60}초`;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-display">실행 기록</h1>
        {/* 시간 필터 */}
        <div className="flex items-center gap-1 rounded-lg bg-muted p-1">
          {timeFilters.map((f) => (
            <button
              key={f.value}
              onClick={() => setFilter(f.value)}
              className={`px-3 py-1 rounded-md text-xs transition-colors ${
                filter === f.value
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* 일별 차트 */}
      {dailyData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">
              일별 실행 횟수 / 에러율
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-56">
              {mounted ? (
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={dailyData}>
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="rgba(255,255,255,0.06)"
                    />
                    <XAxis
                      dataKey="date"
                      tick={{ fontSize: 10, fill: "#71717a" }}
                      axisLine={{ stroke: "rgba(255,255,255,0.06)" }}
                    />
                    <YAxis
                      yAxisId="left"
                      tick={{ fontSize: 10, fill: "#71717a" }}
                      axisLine={{ stroke: "rgba(255,255,255,0.06)" }}
                    />
                    <YAxis
                      yAxisId="right"
                      orientation="right"
                      domain={[0, 100]}
                      tick={{ fontSize: 10, fill: "#71717a" }}
                      axisLine={{ stroke: "rgba(255,255,255,0.06)" }}
                      unit="%"
                    />
                    <Tooltip
                      contentStyle={{
                        background: "#121212",
                        border: "1px solid rgba(255,255,255,0.08)",
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                    />
                    <Bar
                      yAxisId="left"
                      dataKey="total"
                      name="실행 횟수"
                      fill="#2977f5"
                      radius={[4, 4, 0, 0]}
                    />
                    <Bar
                      yAxisId="left"
                      dataKey="failed"
                      name="실패"
                      fill="#ef4444"
                      radius={[4, 4, 0, 0]}
                      style={{
                        filter: "drop-shadow(0 0 4px rgba(239,68,68,0.4))",
                      }}
                    />
                    <Line
                      yAxisId="right"
                      type="monotone"
                      dataKey="errorRate"
                      name="에러율(%)"
                      stroke="#f97316"
                      strokeWidth={2}
                      dot={false}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full w-full" />
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* 실행 테이블 */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-8 space-y-3">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="h-10 animate-pulse rounded bg-muted" />
              ))}
            </div>
          ) : (
            <Table className="table-fixed">
              <colgroup>
                <col style={{ width: "10%" }} />
                <col style={{ width: "17%" }} />
                <col style={{ width: "20%" }} />
                <col style={{ width: "18%" }} />
                <col style={{ width: "13%" }} />
                <col style={{ width: "9%" }} />
                <col style={{ width: "13%" }} />
              </colgroup>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-center">상태</TableHead>
                  <TableHead className="text-center">실행 정보</TableHead>
                  <TableHead className="text-center">관련 영상</TableHead>
                  <TableHead className="text-center">슬롯 / 재시도</TableHead>
                  <TableHead className="text-center">시작 시간</TableHead>
                  <TableHead className="text-center">소요시간</TableHead>
                  <TableHead className="text-center">세부 내용</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredRuns.map((run) => {
                  const metaLines = summarizeRunMeta(run);

                  return (
                  <TableRow key={run.id}>
                    <TableCell className="text-center align-top">
                      <StatusBadge status={run.status} />
                    </TableCell>
                    <TableCell className="align-top">
                      <div className="flex flex-col items-center gap-1.5 py-0.5">
                        <Badge variant="outline" className="text-[10px]">
                          {typeLabels[run.run_type] || run.run_type}
                        </Badge>
                        <Badge variant="secondary" className="text-[10px]">
                          {triggerLabels[run.trigger_source || "manual"] ||
                            run.trigger_source ||
                            "수동"}
                        </Badge>
                        {run.failure_stage && (
                          <span className="text-[10px] text-red-400">
                            stage: {run.failure_stage}
                          </span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="align-top">
                      <div className="space-y-1 py-0.5 text-center">
                        {run.video_id ? (
                          <Link
                            href={`/videos/${run.video_id}`}
                            className="text-xs text-blue-400 hover:text-blue-300 transition-colors break-all"
                          >
                            {metaLines.find((line) => line.startsWith("제목:"))?.replace(
                              "제목: ",
                              ""
                            ) || run.video_id}
                          </Link>
                        ) : (
                          <span className="text-xs text-muted-foreground">-</span>
                        )}
                        {run.video_id && (
                          <p className="text-[10px] text-muted-foreground break-all">
                            {run.video_id}
                          </p>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="align-top">
                      <div className="space-y-1 py-0.5 text-center">
                        <p className="text-xs text-foreground/85 break-all">
                          {run.slot_key || "-"}
                        </p>
                        <p className="text-[10px] text-muted-foreground">
                          재시도 {run.retry_count ?? 0}회
                        </p>
                      </div>
                    </TableCell>
                    <TableCell className="text-center text-xs text-muted-foreground align-top">
                      {format(parseISO(run.started_at), "MM/dd HH:mm:ss", {
                        locale: ko,
                      })}
                    </TableCell>
                    <TableCell className="text-center text-xs align-top">
                      {formatDuration(run)}
                    </TableCell>
                    <TableCell className="align-top">
                      {run.error_message ? (
                        <p className="py-0.5 text-xs text-red-400 break-all">
                          {run.error_message}
                        </p>
                      ) : metaLines.length > 0 ? (
                        <div className="space-y-1 py-0.5">
                          {metaLines.slice(0, 3).map((line) => (
                            <p
                              key={line}
                              className="text-xs text-muted-foreground break-all"
                            >
                              {line}
                            </p>
                          ))}
                        </div>
                      ) : (
                        <p className="py-0.5 text-xs text-muted-foreground text-center">
                          -
                        </p>
                      )}
                    </TableCell>
                  </TableRow>
                )})}
                {filteredRuns.length === 0 && (
                  <TableRow>
                    <TableCell
                      colSpan={7}
                      className="text-center py-8 text-sm text-muted-foreground"
                    >
                      실행 기록이 없습니다
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
