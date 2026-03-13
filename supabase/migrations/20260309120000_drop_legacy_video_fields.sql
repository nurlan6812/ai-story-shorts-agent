drop index if exists public.idx_videos_upload_status;

alter table public.videos
    drop column if exists hook_text,
    drop column if exists upload_status;

comment on column public.videos.publish_status is 'publication lifecycle status: ready/queued/uploading/uploaded/failed';
