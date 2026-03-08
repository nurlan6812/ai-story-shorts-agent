"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Video,
  BarChart3,
  History,
  Settings,
} from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "대시보드", icon: LayoutDashboard },
  { href: "/videos", label: "영상 관리", icon: Video },
  { href: "/analytics", label: "성과 분석", icon: BarChart3 },
  { href: "/runs", label: "실행 기록", icon: History },
  { href: "/control", label: "시스템 제어", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 z-30 flex h-screen w-56 flex-col border-r border-border bg-card">
      {/* 로고 */}
      <div className="flex h-14 items-center gap-2 border-b border-border px-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-500 text-sm font-bold text-white">
          YT
        </div>
        <div>
          <p className="text-sm font-semibold">썰알람</p>
          <p className="text-[10px] text-muted-foreground">관제 대시보드</p>
        </div>
      </div>

      {/* 네비게이션 */}
      <nav className="flex-1 space-y-1 p-3">
        {navItems.map((item) => {
          const isActive =
            pathname === item.href ||
            (item.href !== "/" && pathname.startsWith(item.href));
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                isActive
                  ? "bg-blue-500/10 text-blue-400 font-medium"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground"
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* 하단 정보 */}
      <div className="border-t border-border p-3">
        <p className="text-[10px] text-muted-foreground text-center">
          v1.0.0 · 로컬 관제
        </p>
      </div>
    </aside>
  );
}
