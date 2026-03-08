"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import { Sparkles, BarChart3 } from "lucide-react";

export function ManualGenerate() {
  const [topic, setTopic] = useState("");
  const [genLoading, setGenLoading] = useState(false);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [message, setMessage] = useState("");

  async function handleGenerate() {
    setGenLoading(true);
    setMessage("");
    try {
      await apiFetch("/api/generate/trigger", {
        method: "POST",
        body: JSON.stringify({ topic }),
      });
      setMessage("영상 생성이 백그라운드에서 시작되었습니다");
      setTopic("");
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "오류 발생");
    } finally {
      setGenLoading(false);
    }
  }

  async function handleAnalytics() {
    setAnalyticsLoading(true);
    setMessage("");
    try {
      await apiFetch("/api/generate/analytics", { method: "POST" });
      setMessage("애널리틱스 수집이 시작되었습니다");
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "오류 발생");
    } finally {
      setAnalyticsLoading(false);
    }
  }

  return (
    <Card className="glow-border">
      <CardHeader>
        <CardTitle className="text-sm font-medium">수동 실행</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 영상 생성 */}
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">영상 생성</p>
          <div className="flex gap-2">
            <Input
              placeholder="토픽 (비워두면 자동)"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              className="h-8 text-sm"
            />
            <Button
              size="sm"
              onClick={handleGenerate}
              disabled={genLoading}
              className="gap-1.5 shrink-0"
            >
              <Sparkles className="h-3 w-3" />
              {genLoading ? "생성중..." : "생성"}
            </Button>
          </div>
        </div>

        {/* 애널리틱스 수집 */}
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">애널리틱스 수집</p>
          <Button
            variant="outline"
            size="sm"
            onClick={handleAnalytics}
            disabled={analyticsLoading}
            className="gap-1.5"
          >
            <BarChart3 className="h-3 w-3" />
            {analyticsLoading ? "수집중..." : "수동 수집"}
          </Button>
        </div>

        {message && <p className="text-xs text-blue-400">{message}</p>}
      </CardContent>
    </Card>
  );
}
