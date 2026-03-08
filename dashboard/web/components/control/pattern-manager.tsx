"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { useSupabaseQuery } from "@/hooks/use-supabase-query";
import { supabase } from "@/lib/supabase";
import type { Pattern } from "@/lib/types";

const typeLabels: Record<string, string> = {
  hook: "후크",
  style: "스타일",
  topic: "토픽",
  avoid: "회피",
  recommendation: "추천",
};

export function PatternManager() {
  const { data: patterns, refetch } = useSupabaseQuery<Pattern>({
    table: "patterns",
    order: { column: "win_rate", ascending: false },
  });

  async function togglePattern(id: string, isActive: boolean) {
    await supabase
      .from("patterns")
      .update({ is_active: isActive })
      .eq("id", id);
    refetch();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">패턴 관리</CardTitle>
      </CardHeader>
      <CardContent>
        {patterns.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-8">
            등록된 패턴이 없습니다
          </p>
        ) : (
          <div className="space-y-2">
            {patterns.map((p) => (
              <div
                key={p.id}
                className="flex items-center justify-between rounded-lg px-3 py-2.5 hover:bg-accent/50 transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <Switch
                    checked={p.is_active}
                    onCheckedChange={(checked) => togglePattern(p.id, checked)}
                  />
                  <div className="min-w-0">
                    <p className="text-sm truncate">{p.pattern_key}</p>
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <Badge variant="outline" className="text-[9px] px-1">
                        {typeLabels[p.pattern_type] || p.pattern_type}
                      </Badge>
                      <span className="text-[10px] text-muted-foreground">
                        승률 {(p.win_rate * 100).toFixed(0)}% · n={p.sample_size}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
