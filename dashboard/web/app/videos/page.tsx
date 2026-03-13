"use client";

import { useState, useMemo } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { VideoTable } from "@/components/videos/video-table";
import { VideoFilters } from "@/components/videos/video-filters";
import { useSupabaseQuery } from "@/hooks/use-supabase-query";
import { Upload, Loader2, AlertTriangle, CalendarClock } from "lucide-react";
import type { Video, Analytics } from "@/lib/types";

export type VideoWithAnalytics = Video & { analytics: Analytics | null };

function hasScheduledPublish(video: Video) {
  const status = video.publish_status;
  const isPendingPublish =
    status === "ready" || status === "queued" || status === "uploading";
  return isPendingPublish && !!video.publish_after;
}

export default function VideosPage() {
  const [status, setStatus] = useState("all");
  const [view, setView] = useState("all");
  const [search, setSearch] = useState("");

  const { data: videos, loading } = useSupabaseQuery<Video>({
    table: "videos",
    order: { column: "created_at", ascending: false },
    limit: 100,
  });

  const { data: analytics } = useSupabaseQuery<Analytics>({
    table: "analytics",
    order: { column: "fetched_at", ascending: false },
  });

  // 영상별 최신 analytics 조인
  const videosWithAnalytics = useMemo(() => {
    const analyticsMap = new Map<string, Analytics>();
    // fetched_at desc이므로 첫 번째가 최신 — 이미 있으면 skip
    analytics.forEach((a) => {
      if (!analyticsMap.has(a.video_id)) {
        analyticsMap.set(a.video_id, a);
      }
    });
    return videos.map((v) => ({
      ...v,
      analytics: analyticsMap.get(v.id) || null,
    }));
  }, [videos, analytics]);

  const filtered = useMemo(() => {
    let result = videosWithAnalytics;
    if (status !== "all") {
      result = result.filter((v) => v.publish_status === status);
    }
    if (view === "scheduled") {
      result = result.filter(
        (v) => v.publish_status === "queued" || hasScheduledPublish(v)
      );
      result = [...result].sort((a, b) => {
        const aTime = a.publish_after ? Date.parse(a.publish_after) : Number.MAX_SAFE_INTEGER;
        const bTime = b.publish_after ? Date.parse(b.publish_after) : Number.MAX_SAFE_INTEGER;
        return aTime - bTime;
      });
    }
    if (view === "series") {
      result = result.filter((v) => v.is_series);
    }
    if (search) {
      const q = search.toLowerCase();
      result = result.filter((v) =>
        [v.title, v.series_title || ""].some((value) =>
          value.toLowerCase().includes(q)
        )
      );
    }
    return result;
  }, [videosWithAnalytics, status, search]);

  const stats = useMemo(() => {
    const uploaded = videos.filter((v) => v.publish_status === "uploaded").length;
    const queued = videos.filter((v) => {
      const status = v.publish_status;
      return status === "ready" || status === "queued" || status === "uploading";
    }).length;
    const scheduled = videos.filter(
      (v) => v.publish_status === "queued" || hasScheduledPublish(v)
    ).length;
    const failed = videos.filter((v) => v.publish_status === "failed").length;
    return { uploaded, queued, scheduled, failed };
  }, [videos]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-display">영상 관리</h1>
        <span className="text-sm text-muted-foreground">
          총 {filtered.length}개
        </span>
      </div>

      {/* 통계 요약 패널 */}
      <div className="grid grid-cols-4 gap-3">
        <Card className="glow-border">
          <CardContent className="flex items-center gap-3 py-3 px-4">
            <Upload className="h-4 w-4 text-emerald-400" />
            <div>
              <p className="text-lg font-bold">{stats.uploaded}</p>
              <p className="text-[10px] text-muted-foreground">업로드 완료</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-3 py-3 px-4">
            <Loader2 className="h-4 w-4 text-blue-400" />
            <div>
              <p className="text-lg font-bold">{stats.queued}</p>
              <p className="text-[10px] text-muted-foreground">업로드 대기</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-3 py-3 px-4">
            <CalendarClock className="h-4 w-4 text-violet-400" />
            <div>
              <p className="text-lg font-bold">{stats.scheduled}</p>
              <p className="text-[10px] text-muted-foreground">예약 발행</p>
            </div>
          </CardContent>
        </Card>
        <Card className={stats.failed > 0 ? "glow-border-red" : ""}>
          <CardContent className="flex items-center gap-3 py-3 px-4">
            <AlertTriangle className={`h-4 w-4 ${stats.failed > 0 ? "text-red-400" : "text-muted-foreground"}`} />
            <div>
              <p className="text-lg font-bold">{stats.failed}</p>
              <p className="text-[10px] text-muted-foreground">실패</p>
            </div>
          </CardContent>
        </Card>
      </div>

      <VideoFilters
        status={status}
        view={view}
        search={search}
        onStatusChange={setStatus}
        onViewChange={setView}
        onSearchChange={setSearch}
      />

      <Card>
        {loading ? (
          <div className="p-8 space-y-3">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-muted" />
            ))}
          </div>
        ) : (
          <VideoTable videos={filtered} />
        )}
      </Card>
    </div>
  );
}
