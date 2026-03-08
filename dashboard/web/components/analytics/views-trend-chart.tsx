"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { format, parseISO } from "date-fns";
import type { Video, Analytics } from "@/lib/types";

interface Props {
  data: (Video & { analytics: Analytics | null })[];
}

export function ViewsTrendChart({ data }: Props) {
  const chartData = data.map((v) => ({
    date: format(parseISO(v.created_at), "MM/dd"),
    title: v.title.slice(0, 20),
    views: v.analytics?.views ?? 0,
    likes: v.analytics?.likes ?? 0,
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">
          조회수 / 좋아요 트렌드
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-72 chart-glow-blue">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(255,255,255,0.06)"
              />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11, fill: "#71717a" }}
                axisLine={{ stroke: "rgba(255,255,255,0.06)" }}
              />
              <YAxis
                tick={{ fontSize: 11, fill: "#71717a" }}
                axisLine={{ stroke: "rgba(255,255,255,0.06)" }}
              />
              <Tooltip
                contentStyle={{
                  background: "#121212",
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 8,
                  fontSize: 12,
                }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line
                type="monotone"
                dataKey="views"
                name="조회수"
                stroke="#2977f5"
                strokeWidth={2}
                dot={{ r: 3, fill: "#2977f5" }}
              />
              <Line
                type="monotone"
                dataKey="likes"
                name="좋아요"
                stroke="#10b981"
                strokeWidth={2}
                dot={{ r: 3, fill: "#10b981" }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
