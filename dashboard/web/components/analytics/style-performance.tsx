"use client";

import { useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { Video, Analytics } from "@/lib/types";
import { useHasMounted } from "@/hooks/use-has-mounted";

interface Props {
  data: (Video & { analytics: Analytics | null })[];
  groupBy:
    | "style"
    | "bgm_mood"
    | "story_type"
    | "source_region"
    | "emotion"
    | "ending_type"
    | "scene_density"
    | "series_format";
  title: string;
}

function getGroupValue(
  video: Video & { analytics: Analytics | null },
  groupBy: Props["groupBy"]
) {
  switch (groupBy) {
    case "emotion": {
      const emotion = video.research_brief?.emotion;
      return typeof emotion === "string" && emotion ? emotion : "미지정";
    }
    case "series_format":
      return video.is_series ? "series" : "single";
    case "scene_density": {
      const sceneCount = video.scene_count ?? 0;
      if (sceneCount <= 0) return "미지정";
      if (sceneCount <= 7) return "low";
      if (sceneCount <= 9) return "medium";
      return "high";
    }
    default:
      return video[groupBy] || "미지정";
  }
}

export function StylePerformance({ data, groupBy, title }: Props) {
  const mounted = useHasMounted();

  const chartData = useMemo(() => {
    const groups = new Map<string, { total: number; count: number }>();
    data.forEach((v) => {
      const key = getGroupValue(v, groupBy);
      const prev = groups.get(key) || { total: 0, count: 0 };
      groups.set(key, {
        total: prev.total + (v.analytics?.views ?? 0),
        count: prev.count + 1,
      });
    });
    return Array.from(groups.entries())
      .map(([name, { total, count }]) => ({
        name,
        avg: Math.round(total / count),
        count,
      }))
      .sort((a, b) => b.avg - a.avg);
  }, [data, groupBy]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-56 chart-glow-blue">
          {mounted ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="rgba(255,255,255,0.06)"
                />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 10, fill: "#71717a" }}
                  axisLine={{ stroke: "rgba(255,255,255,0.06)" }}
                />
                <YAxis
                  tick={{ fontSize: 10, fill: "#71717a" }}
                  axisLine={{ stroke: "rgba(255,255,255,0.06)" }}
                />
                <Tooltip
                  contentStyle={{
                    background: "#121212",
                    border: "1px solid rgba(255,255,255,0.08)",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                  formatter={(value) => [
                    Number(value).toLocaleString(),
                    "평균 조회수",
                  ]}
                />
                <Bar dataKey="avg" fill="#2977f5" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full w-full" />
          )}
        </div>
      </CardContent>
    </Card>
  );
}
