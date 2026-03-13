"use client";

import { useState, useMemo } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { useSupabaseQuery } from "@/hooks/use-supabase-query";
import type { Video, Analytics, Pattern } from "@/lib/types";
import { ViewsTrendChart } from "@/components/analytics/views-trend-chart";
import { StylePerformance } from "@/components/analytics/style-performance";
import { PatternWinRates } from "@/components/analytics/pattern-win-rates";
import { BestWorstTable } from "@/components/analytics/best-worst-table";
import {
  Eye,
  MousePointerClick,
  Clock,
  ThumbsUp,
} from "lucide-react";
import { parseISO, subDays, subMonths, isAfter } from "date-fns";

const periods = [
  { label: "30일", value: "30d" },
  { label: "90일", value: "90d" },
  { label: "1년", value: "1y" },
] as const;

type Period = (typeof periods)[number]["value"];

export default function AnalyticsPage() {
  const [period, setPeriod] = useState<Period>("30d");

  const { data: videos } = useSupabaseQuery<Video>({
    table: "videos",
    select: "id,title,style,bgm_mood,publish_status,story_type,source_region,is_series,part_number,part_count,ending_type,scene_count,research_brief,youtube_id,created_at",
    filter: { column: "publish_status", value: "uploaded" },
    order: { column: "created_at", ascending: true },
  });

  const { data: analytics } = useSupabaseQuery<Analytics>({
    table: "analytics",
    order: { column: "fetched_at", ascending: true },
  });

  const { data: patterns } = useSupabaseQuery<Pattern>({
    table: "patterns",
    order: { column: "win_rate", ascending: false },
  });

  // 기간 필터 적용
  const cutoff = useMemo(() => {
    const now = new Date();
    switch (period) {
      case "30d":
        return subDays(now, 30);
      case "90d":
        return subDays(now, 90);
      case "1y":
        return subMonths(now, 12);
    }
  }, [period]);

  // 영상+성과 데이터 조인 (기간 필터 적용)
  const videosWithAnalytics = useMemo(() => {
    const analyticsMap = new Map<string, Analytics>();
    analytics.forEach((a) => analyticsMap.set(a.video_id, a));
    return videos
      .filter((v) => isAfter(parseISO(v.created_at), cutoff))
      .map((v) => ({
        ...v,
        analytics: analyticsMap.get(v.id) || null,
      }))
      .filter((v) => v.analytics !== null);
  }, [videos, analytics, cutoff]);

  // KPI 계산
  const kpi = useMemo(() => {
    if (videosWithAnalytics.length === 0) {
      return { totalViews: 0, avgCtr: 0, avgViewedRate: 0, totalLikes: 0 };
    }
    let totalViews = 0;
    let totalCtr = 0;
    let totalViewedRate = 0;
    let totalLikes = 0;
    videosWithAnalytics.forEach((v) => {
      if (v.analytics) {
        totalViews += v.analytics.views;
        totalCtr += v.analytics.ctr;
        totalViewedRate += v.analytics.avg_percentage_viewed;
        totalLikes += v.analytics.likes;
      }
    });
    const count = videosWithAnalytics.length;
    return {
      totalViews,
      avgCtr: (totalCtr / count) * 100,
      avgViewedRate: totalViewedRate / count,
      totalLikes,
    };
  }, [videosWithAnalytics]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-display">성과 분석</h1>
        {/* 기간 선택 탭 */}
        <div className="flex items-center gap-1 rounded-lg bg-muted p-1">
          {periods.map((p) => (
            <button
              key={p.value}
              onClick={() => setPeriod(p.value)}
              className={`px-3 py-1 rounded-md text-xs transition-colors ${
                period === p.value
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* 4열 KPI 카드 */}
      <div className="grid grid-cols-4 gap-4">
        <Card className="glow-border">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center gap-2 mb-1">
              <Eye className="h-4 w-4 text-blue-400" />
              <p className="text-xs text-muted-foreground">총 조회수</p>
            </div>
            <p className="text-2xl font-bold">
              {kpi.totalViews.toLocaleString()}
            </p>
          </CardContent>
        </Card>
        <Card className="glow-border">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center gap-2 mb-1">
              <MousePointerClick className="h-4 w-4 text-emerald-400" />
              <p className="text-xs text-muted-foreground">평균 CTR</p>
            </div>
            <p className="text-2xl font-bold">{kpi.avgCtr.toFixed(1)}%</p>
          </CardContent>
        </Card>
        <Card className="glow-border">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center gap-2 mb-1">
              <Clock className="h-4 w-4 text-purple-400" />
              <p className="text-xs text-muted-foreground">평균 시청률</p>
            </div>
            <p className="text-2xl font-bold">
              {kpi.avgViewedRate.toFixed(0)}%
            </p>
          </CardContent>
        </Card>
        <Card className="glow-border">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center gap-2 mb-1">
              <ThumbsUp className="h-4 w-4 text-pink-400" />
              <p className="text-xs text-muted-foreground">총 좋아요</p>
            </div>
            <p className="text-2xl font-bold">
              {kpi.totalLikes.toLocaleString()}
            </p>
          </CardContent>
        </Card>
      </div>

      {videosWithAnalytics.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            성과 데이터가 아직 수집되지 않았습니다. 업로드 후 48시간 이후 자동
            수집됩니다.
          </CardContent>
        </Card>
      ) : (
        <>
          {/* 트렌드 차트 */}
          <ViewsTrendChart data={videosWithAnalytics} />

          {/* 제작 톤 */}
          <div className="grid grid-cols-2 gap-4">
            <StylePerformance
              data={videosWithAnalytics}
              groupBy="style"
              title="스타일별 평균 조회수"
            />
            <StylePerformance
              data={videosWithAnalytics}
              groupBy="bgm_mood"
              title="BGM별 평균 조회수"
            />
          </div>

          {/* 스토리 특성 */}
          <div className="grid gap-4 lg:grid-cols-3">
            <StylePerformance
              data={videosWithAnalytics}
              groupBy="story_type"
              title="스토리 유형별 평균 조회수"
            />
            <StylePerformance
              data={videosWithAnalytics}
              groupBy="source_region"
              title="소스 지역별 평균 조회수"
            />
            <StylePerformance
              data={videosWithAnalytics}
              groupBy="emotion"
              title="감정 톤별 평균 조회수"
            />
          </div>

          {/* 포맷 특성 */}
          <div className="grid gap-4 lg:grid-cols-3">
            <StylePerformance
              data={videosWithAnalytics}
              groupBy="series_format"
              title="단편/시리즈 평균 조회수"
            />
            <StylePerformance
              data={videosWithAnalytics}
              groupBy="ending_type"
              title="엔딩 타입별 평균 조회수"
            />
            <StylePerformance
              data={videosWithAnalytics}
              groupBy="scene_density"
              title="장면 밀도별 평균 조회수"
            />
          </div>

          {/* 베스트 / 개선필요 */}
          <div className="grid grid-cols-2 gap-4">
            <BestWorstTable data={videosWithAnalytics} type="best" />
            <BestWorstTable data={videosWithAnalytics} type="worst" />
          </div>

          {/* 패턴 승률 */}
          {patterns.length > 0 && <PatternWinRates patterns={patterns} />}
        </>
      )}
    </div>
  );
}
