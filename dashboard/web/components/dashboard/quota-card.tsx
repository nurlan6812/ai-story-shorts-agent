"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Upload } from "lucide-react";
import { PieChart, Pie, Cell, ResponsiveContainer } from "recharts";
import type { HealthStatus } from "@/lib/types";

export function QuotaCard({ health }: { health: HealthStatus | null }) {
  const quota = health?.quota;
  const used = quota?.used ?? 0;
  const limit = quota?.limit ?? 3;
  const remaining = quota?.remaining ?? limit - used;

  const chartData = [
    { name: "사용", value: used },
    { name: "잔여", value: remaining },
  ];

  return (
    <Card className="glow-border">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          업로드 쿼터
        </CardTitle>
        <Upload className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="flex items-center gap-4">
          <div className="relative h-20 w-20">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={chartData}
                  cx="50%"
                  cy="50%"
                  innerRadius={24}
                  outerRadius={36}
                  startAngle={90}
                  endAngle={-270}
                  dataKey="value"
                  stroke="none"
                >
                  <Cell fill="#2977f5" />
                  <Cell fill="rgba(255,255,255,0.06)" />
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="text-sm font-bold">
                {used}/{limit}
              </span>
            </div>
          </div>
          <div>
            <p className="text-2xl font-bold">{remaining}</p>
            <p className="text-xs text-muted-foreground">오늘 잔여</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
