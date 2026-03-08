// Supabase 테이블 타입

export interface Video {
  id: string;
  title: string;
  description: string;
  tags: string[];
  style: string;
  bgm_mood: string;
  hook_text: string;
  summary: string;
  upload_status: "pending" | "uploaded" | "failed";
  youtube_id: string | null;
  published_at: string | null;
  production_plan: Record<string, unknown> | null;
  research_brief: Record<string, unknown> | null;
  created_at: string;
}

export interface Run {
  id: string;
  run_type: "generate" | "collect_analytics" | "analyze";
  status: "running" | "completed" | "failed";
  started_at: string;
  completed_at: string | null;
  video_id: string | null;
  error_message: string | null;
}

export interface Analytics {
  id: string;
  video_id: string;
  fetched_at: string;
  views: number;
  watch_time_minutes: number;
  ctr: number;
  avg_percentage_viewed: number;
  likes: number;
  comments: number;
  shares: number;
  impressions: number;
  subscribers_gained: number;
  subscribers_lost: number;
  duration_seconds: number;
  viewed_rate: number;
  swiped_rate: number;
}

export interface Pattern {
  id: string;
  pattern_type: "hook" | "style" | "topic" | "avoid" | "recommendation";
  pattern_key: string;
  pattern_data: Record<string, unknown>;
  win_rate: number;
  sample_size: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// FastAPI 응답 타입

export interface SchedulerStatus {
  running: boolean;
  pid: number | null;
  next_run: string | null;
}

export interface HealthStatus {
  youtube_token: boolean;
  supabase: boolean;
  disk_free_gb: number;
  quota: {
    remaining: number;
    used: number;
    limit: number;
    can_upload: boolean;
  };
}

export interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
}

export interface LogsResponse {
  logs: LogEntry[];
  total: number;
}
