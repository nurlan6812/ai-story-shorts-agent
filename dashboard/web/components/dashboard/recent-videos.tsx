"use client";

import Link from "next/link";
import Image from "next/image";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/layout/status-badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useSupabaseQuery } from "@/hooks/use-supabase-query";
import { ExternalLink } from "lucide-react";
import type { Video } from "@/lib/types";
import { format, parseISO } from "date-fns";
import { ko } from "date-fns/locale";

function getPublishPlanLabel(video: Video) {
  const isPendingPublish =
    video.publish_status === "ready" ||
    video.publish_status === "queued" ||
    video.publish_status === "uploading";
  if (!isPendingPublish) {
    return null;
  }
  if (video.publish_after) {
    return `예약 ${format(parseISO(video.publish_after), "MM/dd HH:mm", {
      locale: ko,
    })}`;
  }
  if (video.publish_status === "ready") {
    return "즉시 업로드";
  }
  return null;
}

export function RecentVideos() {
  const { data: videos, loading } = useSupabaseQuery<Video>({
    table: "videos",
    order: { column: "created_at", ascending: false },
    limit: 5,
  });

  return (
    <Card className="col-span-2">
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <CardTitle className="text-sm font-medium">최근 영상</CardTitle>
        <Link
          href="/videos"
          className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
        >
          전체보기
        </Link>
      </CardHeader>
      <CardContent className="px-0 pb-0">
        {loading ? (
          <div className="space-y-3 px-6 pb-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-muted" />
            ))}
          </div>
        ) : videos.length === 0 ? (
          <p className="text-sm text-muted-foreground py-8 text-center">
            아직 영상이 없습니다
          </p>
        ) : (
          <Table className="table-fixed">
            <colgroup>
              <col style={{ width: "6%" }} />
              <col style={{ width: "38%" }} />
              <col style={{ width: "12%" }} />
              <col style={{ width: "12%" }} />
              <col style={{ width: "22%" }} />
              <col style={{ width: "10%" }} />
            </colgroup>
            <TableHeader>
              <TableRow>
                <TableHead className="text-center">썸네일</TableHead>
                <TableHead className="text-center">제목</TableHead>
                <TableHead className="text-center">스타일</TableHead>
                <TableHead className="text-center">상태</TableHead>
                <TableHead className="text-center">생성일</TableHead>
                <TableHead className="text-center">YouTube</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {videos.map((v) => (
                <TableRow key={v.id} className="hover:bg-accent/50">
                  <TableCell className="text-center">
                    {v.youtube_id ? (
                      <div className="relative w-12 h-7 rounded overflow-hidden bg-muted shrink-0 mx-auto">
                        <Image
                          src={`https://i.ytimg.com/vi/${v.youtube_id}/hqdefault.jpg`}
                          alt={v.title}
                          fill
                          className="object-cover"
                          sizes="48px"
                          unoptimized
                        />
                      </div>
                    ) : (
                      <div className="w-12 h-7 rounded bg-muted flex items-center justify-center shrink-0 mx-auto">
                        <span className="text-[7px] text-muted-foreground">
                          N/A
                        </span>
                      </div>
                    )}
                  </TableCell>
                  <TableCell className="text-center">
                    <Link
                      href={`/videos/${v.id}`}
                      className="text-sm hover:text-blue-400 transition-colors line-clamp-1"
                    >
                      {v.title}
                    </Link>
                  </TableCell>
                  <TableCell className="text-center">
                    <div className="flex flex-col items-center gap-1">
                      {v.style && (
                        <Badge variant="outline" className="text-[9px] px-1.5">
                          {v.style}
                        </Badge>
                      )}
                      {(v.story_type || v.source_region) && (
                        <span className="text-[10px] text-muted-foreground">
                          {[v.story_type, v.source_region].filter(Boolean).join(" · ")}
                        </span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-center">
                    <div className="flex flex-col items-center gap-1">
                      <StatusBadge status={v.publish_status || "ready"} />
                      {v.is_series && v.part_number && v.part_count && (
                        <Badge variant="outline" className="text-[9px] px-1.5">
                          {v.part_number}/{v.part_count}편
                        </Badge>
                      )}
                      {getPublishPlanLabel(v) && (
                        <span className="text-[10px] text-muted-foreground">
                          {getPublishPlanLabel(v)}
                        </span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-center text-xs text-muted-foreground">
                    {format(parseISO(v.created_at), "yyyy-MM-dd HH:mm", {
                      locale: ko,
                    })}
                  </TableCell>
                  <TableCell className="text-center">
                    {v.youtube_id && (
                      <a
                        href={`https://youtube.com/shorts/${v.youtube_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-400 hover:text-blue-300 inline-flex justify-center"
                      >
                        <ExternalLink className="h-3.5 w-3.5" />
                      </a>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
