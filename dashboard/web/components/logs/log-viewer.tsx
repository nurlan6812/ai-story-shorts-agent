"use client";

import { useEffect, useRef, useState } from "react";
import type { LogEntry } from "@/lib/types";
import { cn } from "@/lib/utils";

const levelColors: Record<string, string> = {
  DEBUG: "text-gray-500",
  INFO: "text-blue-400",
  WARNING: "text-yellow-400",
  ERROR: "text-red-400",
  CRITICAL: "text-red-500 font-bold",
};

const sourceLabels = {
  main: "MAIN",
  recovery: "RECOVERY",
} as const;

const sourceColors = {
  main: "text-cyan-400",
  recovery: "text-amber-400",
} as const;

export function LogViewer({ logs, className }: { logs: LogEntry[]; className?: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [stickToBottom, setStickToBottom] = useState(true);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !stickToBottom) return;
    container.scrollTop = container.scrollHeight;
  }, [logs, stickToBottom]);

  function handleScroll() {
    const container = containerRef.current;
    if (!container) return;

    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    setStickToBottom(distanceFromBottom < 24);
  }

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className={cn("overflow-y-auto rounded-lg bg-[#0a0a0a] border border-border terminal-scrollbar", className || "h-[calc(100vh-16rem)]")}
    >
      <div className="p-4 text-xs leading-relaxed" style={{ fontFamily: "var(--font-mono), ui-monospace, monospace" }}>
        {logs.length === 0 ? (
          <p className="text-muted-foreground text-center py-8">
            로그가 없습니다
          </p>
        ) : (
          logs.map((entry, i) => (
            <div
              key={i}
              className="flex gap-2 hover:bg-white/[0.02] px-1 rounded"
            >
              <span className="text-muted-foreground shrink-0 w-36">
                {entry.timestamp}
              </span>
              <span
                className={cn(
                  "shrink-0 w-20",
                  sourceColors[entry.source] || "text-muted-foreground"
                )}
              >
                {sourceLabels[entry.source] || entry.source}
              </span>
              <span
                className={cn(
                  "shrink-0 w-16",
                  levelColors[entry.level] || "text-muted-foreground"
                )}
              >
                {entry.level}
              </span>
              <span className="text-foreground/80 break-all">
                {entry.message}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
