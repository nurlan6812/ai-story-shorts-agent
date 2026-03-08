"use client";

import Link from "next/link";
import Image from "next/image";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { StatusBadge } from "@/components/layout/status-badge";
import { Badge } from "@/components/ui/badge";
import { ExternalLink, Eye, ThumbsUp, MousePointerClick } from "lucide-react";
import type { Video, Analytics } from "@/lib/types";
import { format, parseISO } from "date-fns";
import { ko } from "date-fns/locale";

type VideoWithAnalytics = Video & { analytics: Analytics | null };

export function VideoTable({ videos }: { videos: VideoWithAnalytics[] }) {
  if (videos.length === 0) {
    return (
      <div className="py-12 text-center text-sm text-muted-foreground">
        영상이 없습니다
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <Table className="table-fixed">
        <colgroup>
          <col style={{ width: "5%" }} />
          <col style={{ width: "27%" }} />
          <col style={{ width: "10%" }} />
          <col style={{ width: "10%" }} />
          <col style={{ width: "10%" }} />
          <col style={{ width: "9%" }} />
          <col style={{ width: "8%" }} />
          <col style={{ width: "13%" }} />
          <col style={{ width: "8%" }} />
        </colgroup>
        <TableHeader>
          <TableRow>
            <TableHead className="text-center">썸네일</TableHead>
            <TableHead className="text-center">제목</TableHead>
            <TableHead className="text-center">스타일</TableHead>
            <TableHead className="text-center">상태</TableHead>
            <TableHead className="text-center">조회수</TableHead>
            <TableHead className="text-center">좋아요</TableHead>
            <TableHead className="text-center">CTR</TableHead>
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
                    <span className="text-[7px] text-muted-foreground">N/A</span>
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
                {v.style && (
                  <Badge variant="outline" className="text-[9px] px-1.5">
                    {v.style}
                  </Badge>
                )}
              </TableCell>
              <TableCell className="text-center">
                <StatusBadge status={v.upload_status} />
              </TableCell>
              <TableCell className="text-center">
                {v.analytics ? (
                  <div className="flex items-center justify-center gap-1">
                    <Eye className="h-3 w-3 text-blue-400 shrink-0" />
                    <span className="text-xs font-medium tabular-nums">
                      {v.analytics.views.toLocaleString()}
                    </span>
                  </div>
                ) : (
                  <span className="text-[10px] text-muted-foreground">-</span>
                )}
              </TableCell>
              <TableCell className="text-center">
                {v.analytics ? (
                  <div className="flex items-center justify-center gap-1">
                    <ThumbsUp className="h-3 w-3 text-pink-400 shrink-0" />
                    <span className="text-xs font-medium tabular-nums">
                      {v.analytics.likes.toLocaleString()}
                    </span>
                  </div>
                ) : (
                  <span className="text-[10px] text-muted-foreground">-</span>
                )}
              </TableCell>
              <TableCell className="text-center">
                {v.analytics ? (
                  <div className="flex items-center justify-center gap-1">
                    <MousePointerClick className="h-3 w-3 text-emerald-400 shrink-0" />
                    <span className="text-xs font-medium tabular-nums">
                      {(v.analytics.ctr * 100).toFixed(1)}%
                    </span>
                  </div>
                ) : (
                  <span className="text-[10px] text-muted-foreground">-</span>
                )}
              </TableCell>
              <TableCell className="text-center text-xs text-muted-foreground">
                {format(parseISO(v.created_at), "MM/dd HH:mm", { locale: ko })}
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
    </div>
  );
}
