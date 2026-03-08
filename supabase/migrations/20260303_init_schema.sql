-- 썰알람 초기 스키마
-- 유머/썰/사연 YouTube Shorts 자동화 파이프라인

-- ============================================================
-- videos: 생성된 영상 메타데이터
-- ============================================================
CREATE TABLE IF NOT EXISTS videos (
    id          uuid PRIMARY KEY,
    title       text NOT NULL DEFAULT '',
    description text DEFAULT '',
    tags        jsonb DEFAULT '[]'::jsonb,
    style       text DEFAULT '',            -- casual, storytelling, darkcomedy, wholesome, absurdist
    bgm_mood    text DEFAULT '',            -- funny, emotional, tension, chill, dramatic, quirky
    hook_text   text DEFAULT '',
    summary     text DEFAULT '',
    upload_status text DEFAULT 'pending',   -- pending, uploaded, failed
    youtube_id  text,
    published_at timestamptz,
    production_plan jsonb,                  -- Director 출력 전체
    research_brief  jsonb,                  -- Researcher 출력 (story_type, emotion, story_points 등)
    created_at  timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_videos_upload_status ON videos(upload_status);
CREATE INDEX IF NOT EXISTS idx_videos_created_at    ON videos(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_videos_published_at  ON videos(published_at DESC);

-- ============================================================
-- runs: 파이프라인 실행 기록
-- ============================================================
CREATE TABLE IF NOT EXISTS runs (
    id           uuid PRIMARY KEY,
    started_at   timestamptz DEFAULT now(),
    completed_at timestamptz,
    status       text DEFAULT 'running',    -- running, completed, failed
    run_type     text DEFAULT 'generate',   -- generate, analyze
    video_id     uuid REFERENCES videos(id),
    error_message text
);

CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_status     ON runs(status);

-- ============================================================
-- analytics: YouTube 성과 데이터
-- ============================================================
CREATE TABLE IF NOT EXISTS analytics (
    id                    uuid PRIMARY KEY,
    video_id              uuid REFERENCES videos(id),
    fetched_at            timestamptz DEFAULT now(),
    views                 int DEFAULT 0,
    watch_time_minutes    float DEFAULT 0,
    ctr                   float DEFAULT 0,
    avg_percentage_viewed float DEFAULT 0,
    likes                 int DEFAULT 0,
    comments              int DEFAULT 0,
    shares                int DEFAULT 0,
    impressions           int DEFAULT 0,
    subscribers_gained    int DEFAULT 0,
    subscribers_lost      int DEFAULT 0,
    duration_seconds      int DEFAULT 0,
    viewed_rate           float DEFAULT 0,
    swiped_rate           float DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_analytics_video_id ON analytics(video_id);

-- ============================================================
-- patterns: 성공 패턴 (Analyzer → Director 피드백 루프)
-- ============================================================
CREATE TABLE IF NOT EXISTS patterns (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    pattern_type  text NOT NULL,            -- hook, style, story_types, emotions, topics, timing, avoid
    pattern_key   text NOT NULL,
    pattern_data  jsonb DEFAULT '{}'::jsonb,
    win_rate      float DEFAULT 0,
    sample_size   int DEFAULT 0,
    is_active     boolean DEFAULT true,
    created_at    timestamptz DEFAULT now(),
    updated_at    timestamptz DEFAULT now(),
    UNIQUE(pattern_type, pattern_key)
);

CREATE INDEX IF NOT EXISTS idx_patterns_active ON patterns(is_active) WHERE is_active = true;
