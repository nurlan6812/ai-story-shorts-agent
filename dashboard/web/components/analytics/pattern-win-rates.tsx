"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { Pattern } from "@/lib/types";

export function PatternWinRates({ patterns }: { patterns: Pattern[] }) {
  const activePatterns = patterns.filter((p) => p.is_active);
  const grouped = activePatterns.reduce(
    (acc, p) => {
      const type = p.pattern_type;
      if (!acc[type]) acc[type] = [];
      acc[type].push(p);
      return acc;
    },
    {} as Record<string, Pattern[]>
  );

  const typeLabels: Record<string, string> = {
    hook: "후크",
    style: "스타일",
    topic: "토픽",
    avoid: "회피",
    recommendation: "추천",
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">패턴 승률</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {Object.entries(grouped).map(([type, items]) => (
          <div key={type}>
            <p className="text-xs font-medium text-muted-foreground mb-2">
              {typeLabels[type] || type}
            </p>
            <div className="space-y-1.5">
              {items.slice(0, 5).map((p) => (
                <div
                  key={p.id}
                  className="flex items-center justify-between text-sm"
                >
                  <span className="truncate max-w-xs">{p.pattern_key}</span>
                  <div className="flex items-center gap-2">
                    <div className="w-24 h-1.5 rounded-full bg-muted">
                      <div
                        className="h-1.5 rounded-full bg-blue-500"
                        style={{ width: `${p.win_rate * 100}%` }}
                      />
                    </div>
                    <span className="text-xs text-muted-foreground w-12 text-right">
                      {(p.win_rate * 100).toFixed(0)}%
                    </span>
                    <Badge variant="outline" className="text-[9px] px-1">
                      n={p.sample_size}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
        {Object.keys(grouped).length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-4">
            활성 패턴이 없습니다
          </p>
        )}
      </CardContent>
    </Card>
  );
}
