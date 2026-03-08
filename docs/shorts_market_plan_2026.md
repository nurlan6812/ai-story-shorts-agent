# YouTube Shorts Market Plan (2026-03)

## 1) Market Snapshot (What matters now)

1. Shorts scale is already proven:
   - YouTube Shorts has sustained around 70B+ daily views.
2. Shorts monetization is no longer experimental:
   - More than 25% of YPP channels are earning via Shorts revenue share.
   - More than 80% of creators who entered YPP through Shorts thresholds also earn via other YPP features.
3. Entry/monetization thresholds are clear:
   - Full ad-revenue route: 1,000 subscribers + 10M valid public Shorts views (last 90 days).
   - Expanded fan-funding route: 500 subscribers + 3M valid public Shorts views (last 90 days).
4. Measurement changed in 2025:
   - Shorts public view counting changed to include every play/replay.
   - YPP eligibility/revenue still relies on "engaged views" in analytics.
5. Audience behavior risk:
   - Teen audience remains extremely short-form heavy (YouTube/TikTok both high usage).
   - For discovery and retention, first 1-3s hook and repeatable format design are still the main leverage points.

## 2) What to copy from ko_storyagent_final prompts

The most useful parts are metadata-first scene design rules, not long prose:

1. Force chronology and role consistency per scene.
2. Encode scene-level visual metadata explicitly:
   - setting (era/place/time/weather hint)
   - emotion beat
   - action beat
3. Separate responsibilities:
   - structure planning
   - image prompting
   - narration writing
4. Keep image prompts visual-only and continuity-aware.

These are now reflected in this repo via:
- `scene_outline`
- `image_intent`
- `setting_hint`
- `emotion_beat`
- `action_beat`

## 3) Recommended Product Structure (for this project)

1. Researcher:
   - Output factual story package only (`topic`, `hook`, `story_points`, `original_title`, `original_story`, `source_region`).
2. Director:
   - Build structural plan only (scene decomposition + camera/effect/transition + scene metadata).
   - Do not write final narration or final image query.
3. Image Agent:
   - Convert metadata to visual prompts (English, character-consistent, era-aware).
4. Narration Agent:
   - Convert metadata to Korean spoken lines (1-2 lines, style guide aware).
5. Composer:
   - Join image + voice + overlays + BGM using scene index contracts.

## 4) Content Portfolio Plan (first 8 weeks)

1. Pillars (weekly mix):
   - Revenge/Satisfying: 30%
   - Relationship Twist: 25%
   - Absurd/Funny Real-life: 25%
   - Touching Family/Friendship: 20%
2. Episode format:
   - 6-9 scenes per video
   - Hook scene in 1st scene mandatory
   - Sub-hook around scene 3-5 mandatory
   - Punchline/cliffhanger in final scene mandatory
3. Publishing cadence:
   - 1-2 Shorts/day, fixed upload windows (2 windows only)
   - 3-video mini-series only when `story_points >= 7` and clear cliffhanger exists

## 5) KPI & Experiment Loop

Primary KPI (per video):
1. 3-second hold rate
2. Completion rate
3. Rewatch signal (avg views per unique viewer proxy)
4. Like/comment/share per 1,000 views

Decision rule:
1. Keep: upper quartile completion + above-median share rate
2. Iterate: good hook but weak mid retention
3. Drop: low hook + low completion for 5+ uploads

Experiment matrix (weekly):
1. Hook style A/B (shock vs curiosity)
2. Scene count A/B (6 vs 8)
3. Narration density A/B (short punch vs descriptive)
4. Camera rhythm A/B (zoom-heavy vs mixed)

## 6) 4-week Engineering Roadmap

Week 1:
1. Lock schema contracts and validation (scene metadata required fields).
2. Add failure fallbacks and structured logs per agent.

Week 2:
1. Add quality gates:
   - image query lint (English/name consistency/era mention)
   - narration lint (length/first-person rule when needed)
2. Add run report artifact per video.

Week 3:
1. Add automated A/B config runner (hook/camera/narration variants).
2. Store per-video feature flags with output metrics.

Week 4:
1. Add feedback learner that updates style/scene heuristics from winners.
2. Promote top performing templates to defaults.

## Sources

- https://blog.youtube/inside-youtube/shorts-revenue-sharing-update/
- https://support.google.com/youtube/answer/72857?hl=en
- https://support.google.com/youtube/answer/15424877?hl=en
- https://support.google.com/youtube/answer/9072033?hl=en
- https://www.pewresearch.org/internet/fact-sheet/social-media/
- https://www.pewresearch.org/internet/2024/12/12/teens-social-media-and-technology-2024/
- https://www.pewresearch.org/short-reads/2025/07/10/10-facts-about-teens-and-social-media/
