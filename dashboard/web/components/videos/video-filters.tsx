"use client";

import { Input } from "@/components/ui/input";
import { Search } from "lucide-react";

const statusOptions = [
  { value: "all", label: "전체" },
  { value: "pending", label: "대기중" },
  { value: "uploaded", label: "업로드됨" },
  { value: "failed", label: "실패" },
];

interface VideoFiltersProps {
  status: string;
  search: string;
  onStatusChange: (status: string) => void;
  onSearchChange: (search: string) => void;
}

export function VideoFilters({
  status,
  search,
  onStatusChange,
  onSearchChange,
}: VideoFiltersProps) {
  return (
    <div className="flex items-center gap-3">
      {/* 상태 필터 */}
      <div className="flex items-center gap-1 rounded-lg bg-muted p-1">
        {statusOptions.map((opt) => (
          <button
            key={opt.value}
            onClick={() => onStatusChange(opt.value)}
            className={`px-3 py-1 rounded-md text-xs transition-colors ${
              status === opt.value
                ? "bg-card text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* 제목 검색 */}
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
        <Input
          placeholder="제목 검색..."
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="pl-8 h-8 w-60 text-sm"
        />
      </div>
    </div>
  );
}
