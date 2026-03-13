"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/layout/status-badge";
import { apiFetch } from "@/lib/api";
import {
  ArrowLeft,
  ExternalLink,
  Play,
  Eye,
  ThumbsUp,
  MousePointerClick,
  Clock,
  Sparkles,
  Video,
  Music,
  Hash,
  FileText,
  BarChart3,
} from "lucide-react";
import type { Video as VideoType, Analytics } from "@/lib/types";
import { format, parseISO } from "date-fns";
import { ko } from "date-fns/locale";

export default function VideoDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const [video, setVideo] = useState<VideoType | null>(null);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function fetchData() {
      try {
        const videoParams = new URLSearchParams({
          table: "videos",
          filter_column: "id",
          filter_value: id,
          limit: "1",
        });
        const analyticsParams = new URLSearchParams({
          table: "analytics",
          filter_column: "video_id",
          filter_value: id,
          order_column: "fetched_at",
          ascending: "false",
          limit: "1",
        });

        const [videoRes, analyticsRes] = await Promise.all([
          apiFetch<{ data: VideoType[] }>(`/api/data/query?${videoParams.toString()}`),
          apiFetch<{ data: Analytics[] }>(
            `/api/data/query?${analyticsParams.toString()}`
          ),
        ]);

        if (cancelled) return;

        setVideo(videoRes.data[0] || null);
        setAnalytics(analyticsRes.data[0] || null);
      } catch {
        if (cancelled) return;
        setVideo(null);
        setAnalytics(null);
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    fetchData();
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-48 animate-pulse rounded bg-muted" />
        <div className="h-96 animate-pulse rounded-lg bg-muted" />
      </div>
    );
  }

  if (!video) {
    return (
      <div className="py-12 text-center text-muted-foreground">
        영상을 찾을 수 없습니다
      </div>
    );
  }

  // 영상 ID 포맷 (VD-YYYY-MMDD-XX)
  const createdDate = parseISO(video.created_at);
  const videoIdLabel = `VD-${format(createdDate, "yyyy-MMdd")}-${id.slice(0, 2).toUpperCase()}`;

  // 영상 길이 포맷
  const durationLabel = analytics?.duration_seconds
    ? `${Math.floor(analytics.duration_seconds / 60)}:${String(analytics.duration_seconds % 60).padStart(2, "0")}`
    : "0:59";
  const publishedDate = video.published_at ? parseISO(video.published_at) : null;
  const headerTimestampLabel = publishedDate
    ? format(publishedDate, "yyyy년 MM월 dd일 HH:mm 업로드", {
        locale: ko,
      })
    : format(createdDate, "yyyy년 MM월 dd일 HH:mm 생성", {
        locale: ko,
      });

  // 참여율 계산
  const engagementRate =
    analytics && analytics.views > 0
      ? ((analytics.likes / analytics.views) * 100).toFixed(1)
      : "0.0";

  return (
    <div className="space-y-5">
      {/* 헤더 영역 */}
      <div className="space-y-3">
        {/* 브레드크럼 + 액션 버튼 */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm">
            <Link
              href="/videos"
              className="flex items-center gap-1.5 text-muted-foreground hover:text-foreground transition-colors"
            >
              <ArrowLeft className="h-4 w-4" />
              영상 목록
            </Link>
            <span className="text-muted-foreground/50">|</span>
            <span className="text-muted-foreground font-mono text-xs">
              ID: {videoIdLabel}
            </span>
          </div>
          <div className="flex items-center gap-2">
            {video.youtube_id && (
              <Button variant="outline" size="sm" asChild>
                <a
                  href={`https://youtube.com/shorts/${video.youtube_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                  YouTube에서 보기
                </a>
              </Button>
            )}
          </div>
        </div>

        {/* 제목 + 상태 */}
        <div>
          <h1 className="text-xl font-display">{video.title}</h1>
          <div className="flex items-center gap-2 mt-1.5">
            <StatusBadge status={video.publish_status || "ready"} />
            <span className="text-xs text-muted-foreground">
              {headerTimestampLabel}
            </span>
          </div>
        </div>
      </div>

      {/* 2컬럼 레이아웃 */}
      <div className="grid grid-cols-3 gap-6">
        {/* 좌: 탭 컨텐츠 (2/3) */}
        <div className="col-span-2">
          <Card>
            <Tabs defaultValue="info">
              <div className="border-b border-border px-4 pt-3">
                <TabsList className="bg-transparent p-0 h-auto gap-0">
                  <TabsTrigger
                    value="info"
                    className="rounded-none border-b-2 border-transparent data-[state=active]:border-blue-500 data-[state=active]:bg-transparent data-[state=active]:shadow-none px-4 pb-2.5 pt-1"
                  >
                    기본 정보
                  </TabsTrigger>
                  <TabsTrigger
                    value="plan"
                    className="rounded-none border-b-2 border-transparent data-[state=active]:border-blue-500 data-[state=active]:bg-transparent data-[state=active]:shadow-none px-4 pb-2.5 pt-1"
                  >
                    프로덕션 플랜
                  </TabsTrigger>
                  <TabsTrigger
                    value="brief"
                    className="rounded-none border-b-2 border-transparent data-[state=active]:border-blue-500 data-[state=active]:bg-transparent data-[state=active]:shadow-none px-4 pb-2.5 pt-1"
                  >
                    리서치 브리프
                  </TabsTrigger>
                  <TabsTrigger
                    value="performance"
                    className="rounded-none border-b-2 border-transparent data-[state=active]:border-blue-500 data-[state=active]:bg-transparent data-[state=active]:shadow-none px-4 pb-2.5 pt-1"
                  >
                    성과 데이터
                  </TabsTrigger>
                </TabsList>
              </div>

              {/* 기본 정보 탭 */}
              <TabsContent value="info" className="mt-0">
                <CardContent className="pt-5 space-y-5">
                  {/* 영상 스타일 + BGM 2컬럼 */}
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                        영상 스타일
                      </p>
                      <div className="flex items-center gap-2">
                        <div className="h-3 w-3 rounded-sm bg-blue-500" />
                        <span className="text-sm font-medium">
                          {video.style || "미지정"}
                        </span>
                      </div>
                    </div>
                    <div className="space-y-1.5">
                      <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                        배경 음악
                      </p>
                      <div className="flex items-center gap-2">
                        <Music className="h-3.5 w-3.5 text-purple-400" />
                        <span className="text-sm font-medium">
                          {video.bgm_mood || "미지정"}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                        스토리 메타
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {video.story_type && (
                          <Badge variant="secondary" className="text-[11px] bg-[#1a1a1a] border border-border">
                            {video.story_type}
                          </Badge>
                        )}
                        {video.source_region && (
                          <Badge variant="secondary" className="text-[11px] bg-[#1a1a1a] border border-border">
                            {video.source_region}
                          </Badge>
                        )}
                        <Badge variant="secondary" className="text-[11px] bg-[#1a1a1a] border border-border">
                          {video.is_series ? "시리즈" : "단편"}
                        </Badge>
                        {video.ending_type && (
                          <Badge variant="secondary" className="text-[11px] bg-[#1a1a1a] border border-border">
                            {video.ending_type}
                          </Badge>
                        )}
                      </div>
                    </div>
                    <div className="space-y-1.5">
                      <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                        운영 상태
                      </p>
                      <div className="space-y-1 text-xs text-foreground/80">
                        <p>생성 상태: {video.generation_status || "미지정"}</p>
                        <p>업로드 상태: {video.publish_status || "미지정"}</p>
                        <p>트리거: {video.trigger_source || "manual"}</p>
                        {video.publish_after && (
                          <p>
                            예약 시각: {format(parseISO(video.publish_after), "yyyy-MM-dd HH:mm", { locale: ko })}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                        시리즈 정보
                      </p>
                      <div className="space-y-1 text-xs text-foreground/80">
                        <p>
                          파트: {video.part_number && video.part_count ? `${video.part_number}/${video.part_count}` : "단편"}
                        </p>
                        <p>시리즈 제목: {video.series_title || "-"}</p>
                      </div>
                    </div>
                    <div className="space-y-1.5">
                      <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                        제작 메타
                      </p>
                      <div className="space-y-1 text-xs text-foreground/80">
                        <p>장면 수: {video.scene_count || "-"}</p>
                        <p>소스 지문: {video.source_fingerprint ? `${video.source_fingerprint.slice(0, 12)}...` : "-"}</p>
                      </div>
                    </div>
                  </div>

                  {/* 핵심 요약 */}
                  <div className="space-y-1.5">
                    <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                      핵심 요약
                    </p>
                    <div className="rounded-lg border border-border bg-[#0a0a0a] p-3.5">
                      <p className="text-sm leading-relaxed text-foreground/90">
                        {video.summary || "요약 정보 없음"}
                      </p>
                    </div>
                  </div>

                  {/* 태그 키워드 */}
                  <div className="space-y-1.5">
                    <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                      <Hash className="h-3 w-3" />
                      태그 키워드
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {video.tags?.length > 0 ? (
                        video.tags.map((tag) => (
                          <Badge
                            key={tag}
                            variant="secondary"
                            className="text-[11px] bg-[#1a1a1a] border border-border hover:bg-[#222] transition-colors"
                          >
                            #{tag}
                          </Badge>
                        ))
                      ) : (
                        <span className="text-sm text-muted-foreground">
                          태그 없음
                        </span>
                      )}
                    </div>
                  </div>

                  {/* 영상 상세 설명 */}
                  <div className="space-y-1.5">
                    <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                      <FileText className="h-3 w-3" />
                      영상 상세 설명
                    </p>
                    <div className="rounded-lg bg-[#0a0a0a] border border-border p-4">
                      <p className="text-xs whitespace-pre-wrap leading-relaxed text-foreground/70">
                        {video.description || "설명 없음"}
                      </p>
                    </div>
                  </div>

                  {/* 푸터: 생성일 + 시스템 */}
                  <div className="flex items-center justify-between pt-3 border-t border-border">
                    <div className="flex items-center gap-1.5">
                      <span className="text-[9px] font-medium text-muted-foreground uppercase tracking-wider">
                        Created at
                      </span>
                      <span className="text-[11px] text-muted-foreground font-mono">
                        {format(createdDate, "yyyy-MM-dd HH:mm:ss")}
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-[9px] font-medium text-muted-foreground uppercase tracking-wider">
                        System
                      </span>
                      <span className="text-[11px] text-muted-foreground font-mono">
                        AI Factory v2.4
                      </span>
                    </div>
                  </div>
                </CardContent>
              </TabsContent>

              {/* 프로덕션 플랜 탭 */}
              <TabsContent value="plan" className="mt-0">
                <CardContent className="pt-5">
                  <pre className="text-xs font-mono text-muted-foreground overflow-auto max-h-[600px] whitespace-pre-wrap rounded-lg bg-[#0a0a0a] border border-border p-4">
                    {video.production_plan
                      ? JSON.stringify(video.production_plan, null, 2)
                      : "프로덕션 플랜 없음"}
                  </pre>
                </CardContent>
              </TabsContent>

              {/* 리서치 브리프 탭 */}
              <TabsContent value="brief" className="mt-0">
                <CardContent className="pt-5">
                  <pre className="text-xs font-mono text-muted-foreground overflow-auto max-h-[600px] whitespace-pre-wrap rounded-lg bg-[#0a0a0a] border border-border p-4">
                    {video.research_brief
                      ? JSON.stringify(video.research_brief, null, 2)
                      : "리서치 브리프 없음"}
                  </pre>
                </CardContent>
              </TabsContent>

              {/* 성과 데이터 탭 */}
              <TabsContent value="performance" className="mt-0">
                <CardContent className="pt-5">
                  {analytics ? (
                    <div className="space-y-4">
                      <div className="grid grid-cols-2 gap-3">
                        <StatRow
                          label="노출수"
                          value={analytics.impressions.toLocaleString()}
                        />
                        <StatRow
                          label="조회수"
                          value={analytics.views.toLocaleString()}
                        />
                        <StatRow
                          label="좋아요"
                          value={analytics.likes.toLocaleString()}
                        />
                        <StatRow
                          label="댓글"
                          value={analytics.comments.toLocaleString()}
                        />
                        <StatRow
                          label="공유"
                          value={analytics.shares.toLocaleString()}
                        />
                        <StatRow
                          label="시청 시간"
                          value={`${analytics.watch_time_minutes.toLocaleString()}분`}
                        />
                        <StatRow
                          label="구독자 획득"
                          value={`+${analytics.subscribers_gained}`}
                        />
                        <StatRow
                          label="구독자 이탈"
                          value={`-${analytics.subscribers_lost}`}
                        />
                      </div>
                      <div className="text-[10px] text-muted-foreground text-right pt-2 border-t border-border">
                        마지막 수집:{" "}
                        {format(
                          parseISO(analytics.fetched_at),
                          "yyyy-MM-dd HH:mm",
                          { locale: ko }
                        )}
                      </div>
                    </div>
                  ) : (
                    <div className="py-8 text-center text-sm text-muted-foreground">
                      <BarChart3 className="h-8 w-8 mx-auto mb-2 text-muted-foreground/50" />
                      성과 데이터가 아직 수집되지 않았습니다
                    </div>
                  )}
                </CardContent>
              </TabsContent>
            </Tabs>
          </Card>
        </div>

        {/* 우: 썸네일 + 메트릭 카드 + 인사이트 (1/3) */}
        <div className="space-y-4">
          {/* 썸네일 프리뷰 — 가로형 컴팩트 */}
          <Card className="overflow-hidden glow-border">
            <div className="relative aspect-video bg-black">
              {video.youtube_id ? (
                <>
                  <Image
                    src={`https://i.ytimg.com/vi/${video.youtube_id}/hqdefault.jpg`}
                    alt={video.title}
                    fill
                    className="object-contain"
                    sizes="320px"
                    unoptimized
                  />
                  {/* 재생 버튼 오버레이 */}
                  <a
                    href={`https://youtube.com/shorts/${video.youtube_id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="absolute inset-0 flex items-center justify-center bg-black/40 hover:bg-black/20 transition-colors"
                  >
                    <div className="h-12 w-12 rounded-full bg-blue-500/90 flex items-center justify-center shadow-lg">
                      <Play className="h-5 w-5 text-white ml-0.5" />
                    </div>
                  </a>
                </>
              ) : (
                <div className="absolute inset-0 flex items-center justify-center">
                  <p className="text-sm text-muted-foreground">썸네일 없음</p>
                </div>
              )}
              {/* 하단 정보 오버레이 */}
              <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent px-3 py-2.5">
                <p className="text-[10px] font-medium text-white/60 uppercase tracking-wider">
                  Preview Thumbnail
                </p>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <span className="text-xs text-white/90 font-mono">
                    {durationLabel} / Shorts
                  </span>
                  <Video className="h-3 w-3 text-white/60" />
                </div>
              </div>
            </div>
          </Card>

          {/* 2x2 메트릭 카드 */}
          {analytics ? (
            <div className="grid grid-cols-2 gap-3">
              <MetricCard
                icon={<Eye className="h-4 w-4 text-blue-400" />}
                label="조회수"
                value={analytics.views.toLocaleString()}
                sub={
                  analytics.impressions > 0
                    ? `노출 대비 ${((analytics.views / analytics.impressions) * 100).toFixed(1)}%`
                    : undefined
                }
                subColor="text-blue-400"
              />
              <MetricCard
                icon={<ThumbsUp className="h-4 w-4 text-pink-400" />}
                label="좋아요"
                value={analytics.likes.toLocaleString()}
                sub={`참여율 ${engagementRate}%`}
                subColor="text-pink-400"
              />
              <MetricCard
                icon={
                  <MousePointerClick className="h-4 w-4 text-emerald-400" />
                }
                label="CTR"
                value={`${(analytics.ctr * 100).toFixed(1)}%`}
                sub={
                  analytics.ctr * 100 > 5
                    ? "상위 25% 도달"
                    : analytics.ctr * 100 > 3
                      ? "평균 수준"
                      : "개선 필요"
                }
                subColor="text-emerald-400"
              />
              <MetricCard
                icon={<Clock className="h-4 w-4 text-purple-400" />}
                label="평균 시청률"
                value={`${analytics.avg_percentage_viewed.toFixed(0)}%`}
                sub={
                  analytics.avg_percentage_viewed > 60
                    ? "높은 몰입도"
                    : analytics.avg_percentage_viewed > 40
                      ? "평균 수준"
                      : "개선 필요"
                }
                subColor="text-purple-400"
              />
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              <MetricCard
                icon={<Eye className="h-4 w-4 text-blue-400/40" />}
                label="조회수"
                value="-"
              />
              <MetricCard
                icon={<ThumbsUp className="h-4 w-4 text-pink-400/40" />}
                label="좋아요"
                value="-"
              />
              <MetricCard
                icon={
                  <MousePointerClick className="h-4 w-4 text-emerald-400/40" />
                }
                label="CTR"
                value="-"
              />
              <MetricCard
                icon={<Clock className="h-4 w-4 text-purple-400/40" />}
                label="평균 시청률"
                value="-"
              />
            </div>
          )}

          {/* 스마트 인사이트 카드 */}
          <Card className="bg-gradient-to-br from-[#1a2744] to-[#121830] border-blue-500/20">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-blue-400" />
                스마트 인사이트
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {analytics ? (
                <>
                  <ul className="text-xs text-foreground/70 space-y-1.5">
                    {analytics.ctr * 100 > 5 ? (
                      <li>
                        CTR {(analytics.ctr * 100).toFixed(1)}%로 양호합니다
                      </li>
                    ) : (
                      <li>
                        CTR 개선이 필요합니다 (현재{" "}
                        {(analytics.ctr * 100).toFixed(1)}%)
                      </li>
                    )}
                    {analytics.avg_percentage_viewed > 60 ? (
                      <li>
                        시청률 {analytics.avg_percentage_viewed.toFixed(0)}%로
                        콘텐츠 몰입도가 높습니다
                      </li>
                    ) : (
                      <li>
                        시청률 개선을 위해 초반 후크 강화를 고려하세요
                      </li>
                    )}
                    {analytics.subscribers_gained > 0 && (
                      <li>
                        구독자 +{analytics.subscribers_gained}명 획득
                      </li>
                    )}
                  </ul>
                  <Link
                    href="/analytics"
                    className="flex items-center justify-center gap-1.5 w-full text-xs text-blue-400 hover:text-blue-300 transition-colors bg-blue-500/10 hover:bg-blue-500/15 rounded-md py-2"
                  >
                    <BarChart3 className="h-3 w-3" />
                    성과 보고서 상세 보기
                  </Link>
                </>
              ) : (
                <p className="text-xs text-foreground/50">
                  데이터 수집 후 인사이트가 표시됩니다
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between rounded-lg bg-[#0a0a0a] border border-border px-3 py-2">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-sm font-medium tabular-nums">{value}</span>
    </div>
  );
}

function MetricCard({
  icon,
  label,
  value,
  sub,
  subColor,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
  subColor?: string;
}) {
  return (
    <Card className="glow-border">
      <CardContent className="pt-3 pb-2.5 px-3">
        <div className="flex items-center gap-2 mb-1">{icon}</div>
        <p className="text-lg font-bold tabular-nums">{value}</p>
        <p className="text-[10px] text-muted-foreground">{label}</p>
        {sub && (
          <p className={`text-[9px] mt-0.5 ${subColor || "text-muted-foreground"}`}>
            {sub}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
