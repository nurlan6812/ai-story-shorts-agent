"use client";

import Link from "next/link";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { AlertTriangle, History, X } from "lucide-react";
import { useSupabaseQuery } from "@/hooks/use-supabase-query";
import type { Run } from "@/lib/types";
import { format, parseISO } from "date-fns";
import { ko } from "date-fns/locale";

export function ErrorSummary() {
  const { data: failedRuns } = useSupabaseQuery<Run>({
    table: "runs",
    filter: { column: "status", value: "failed" },
    order: { column: "started_at", ascending: false },
    limit: 5,
  });

  const [dismissed, setDismissed] = useState<Set<string>>(new Set());

  const visibleRuns = failedRuns.filter((r) => !dismissed.has(r.id));
  const hasErrors = visibleRuns.length > 0;

  function handleDismiss(id: string) {
    setDismissed((prev) => new Set(prev).add(id));
  }

  return (
    <Card className={hasErrors ? "glow-border-red" : ""}>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          최근 에러
        </CardTitle>
        <AlertTriangle
          className={`h-4 w-4 ${hasErrors ? "text-red-400" : "text-muted-foreground"}`}
        />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{visibleRuns.length}</div>
        {visibleRuns.length > 0 ? (
          <div className="mt-2 space-y-2">
            {visibleRuns.slice(0, 3).map((run) => (
              <div key={run.id} className="text-xs">
                <p className="text-red-400 truncate">
                  {run.error_message || "알 수 없는 오류"}
                </p>
                <div className="flex items-center justify-between mt-1">
                  <p className="text-[10px] text-muted-foreground">
                    {format(parseISO(run.started_at), "MM/dd HH:mm", {
                      locale: ko,
                    })}
                  </p>
                  <div className="flex gap-1">
                    <Button
                      asChild
                      variant="ghost"
                      size="icon"
                      className="h-5 w-5 text-muted-foreground hover:text-blue-400"
                      title="실행 기록"
                    >
                      <Link href="/runs">
                        <History className="h-3 w-3" />
                      </Link>
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-5 w-5 text-muted-foreground hover:text-foreground"
                      title="무시"
                      onClick={() => handleDismiss(run.id)}
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-1 text-xs text-muted-foreground">
            최근 에러 없음
          </p>
        )}
      </CardContent>
    </Card>
  );
}
