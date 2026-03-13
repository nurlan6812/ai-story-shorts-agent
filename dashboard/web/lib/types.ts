// Supabase 테이블 타입

export interface Video {
  id: string;
  title: string;
  description: string;
  tags: string[];
  style: string;
  bgm_mood: string;
  summary: string;
  generation_status: "generating" | "generated" | "failed" | null;
  publish_status: "ready" | "queued" | "uploading" | "uploaded" | "failed" | null;
  is_series: boolean | null;
  series_group_id: string | null;
  series_title: string | null;
  part_number: number | null;
  part_count: number | null;
  publish_after: string | null;
  source_fingerprint: string | null;
  story_type: string | null;
  source_region: string | null;
  scene_count: number | null;
  ending_type: string | null;
  trigger_source: string | null;
  youtube_id: string | null;
  published_at: string | null;
  production_plan: Record<string, unknown> | null;
  research_brief: Record<string, unknown> | null;
  created_at: string;
}

export interface Run {
  id: string;
  run_type:
    | "research"
    | "generate"
    | "publish"
    | "collect_analytics"
    | "analyze_patterns";
  status: "running" | "completed" | "failed";
  started_at: string;
  completed_at: string | null;
  video_id: string | null;
  error_message: string | null;
  trigger_source: string | null;
  retry_count: number | null;
  failure_stage: string | null;
  slot_key: string | null;
  run_meta: Record<string, unknown> | null;
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
  pattern_type:
    | "hook"
    | "style"
    | "topic"
    | "story_type"
    | "source_region"
    | "series_format"
    | "emotion"
    | "ending_type"
    | "scene_density"
    | "avoid"
    | "recommendation";
  pattern_key: string;
  pattern_data: Record<string, unknown>;
  win_rate: number;
  sample_size: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// FastAPI 응답 타입

export type SchedulerTarget = "main" | "recovery";
export type LogTarget = "all" | SchedulerTarget;

export interface SchedulerStatus {
  target: SchedulerTarget;
  label: string;
  running: boolean;
  pid: number | null;
  pids: number[];
  next_run: string | null;
  last_log_at: string | null;
  log_path: string;
}

export interface SchedulerOverview {
  main: SchedulerStatus;
  recovery: SchedulerStatus;
}

export interface RecoveryActivity {
  timestamp: string;
  slot: string;
  status:
    | "verified"
    | "retry_triggered"
    | "completed"
    | "failed"
    | "skipped"
    | "info";
  message: string;
  title: string | null;
}

export interface RecoveryActivityResponse {
  activities: RecoveryActivity[];
  total: number;
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
  source: SchedulerTarget;
}

export interface LogsResponse {
  logs: LogEntry[];
  total: number;
  target?: LogTarget;
}
