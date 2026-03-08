import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const statusConfig: Record<string, { label: string; className: string }> = {
  pending: { label: "대기중", className: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20" },
  uploaded: { label: "업로드됨", className: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" },
  failed: { label: "실패", className: "bg-red-500/10 text-red-400 border-red-500/20" },
  running: { label: "실행중", className: "bg-blue-500/10 text-blue-400 border-blue-500/20" },
  completed: { label: "완료", className: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" },
};

export function StatusBadge({ status }: { status: string }) {
  const config = statusConfig[status] || {
    label: status,
    className: "bg-muted text-muted-foreground",
  };

  return (
    <Badge
      variant="outline"
      className={cn("text-[10px] font-medium px-1.5 py-0", config.className)}
    >
      {config.label}
    </Badge>
  );
}
