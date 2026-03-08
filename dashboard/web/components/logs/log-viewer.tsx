"use client";

import { useEffect, useRef } from "react";
import type { LogEntry } from "@/lib/types";
import { cn } from "@/lib/utils";

const levelColors: Record<string, string> = {
  DEBUG: "text-gray-500",
  INFO: "text-blue-400",
  WARNING: "text-yellow-400",
  ERROR: "text-red-400",
  CRITICAL: "text-red-500 font-bold",
};

export function LogViewer({ logs, className }: { logs: LogEntry[]; className?: string }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  return (
    <div className={cn("overflow-y-auto rounded-lg bg-[#0a0a0a] border border-border terminal-scrollbar", className || "h-[calc(100vh-16rem)]")}>
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
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
