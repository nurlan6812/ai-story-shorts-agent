"use client";

import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TrendingUp, TrendingDown } from "lucide-react";
import type { Video, Analytics } from "@/lib/types";

interface Props {
  data: (Video & { analytics: Analytics | null })[];
  type: "best" | "worst";
}

export function BestWorstTable({ data, type }: Props) {
  const sorted = [...data].sort((a, b) => {
    const aViews = a.analytics?.views ?? 0;
    const bViews = b.analytics?.views ?? 0;
    return type === "best" ? bViews - aViews : aViews - bViews;
  });

  const items = sorted.slice(0, 5);
  const isBest = type === "best";

  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-2">
        {isBest ? (
          <TrendingUp className="h-4 w-4 text-emerald-400" />
        ) : (
          <TrendingDown className="h-4 w-4 text-red-400" />
        )}
        <CardTitle className="text-sm font-medium">
          {isBest ? "베스트 영상" : "개선 필요"}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {items.map((v, i) => (
            <Link
              key={v.id}
              href={`/videos/${v.id}`}
              className="flex items-center justify-between rounded-lg px-3 py-2 hover:bg-accent transition-colors"
            >
              <div className="flex items-center gap-3 min-w-0">
                <span className="text-xs text-muted-foreground w-4">
                  {i + 1}
                </span>
                <span className="text-sm truncate">{v.title}</span>
              </div>
              <span className="text-sm font-medium ml-3">
                {(v.analytics?.views ?? 0).toLocaleString()} views
              </span>
            </Link>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
