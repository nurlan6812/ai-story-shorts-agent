"""고급 영상 합성 - 켄 번즈 효과, 전환, 오디오 레이어링"""

import subprocess
import json
from pathlib import Path
from config.settings import VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS, SCENE_GAP


def normalize_audio(audio_path: Path, output_path: Path, target_lufs: float = -16.0, true_peak: float = -3.0) -> Path:
    """오디오 정규화 (loudnorm, 48kHz 리샘플링)

    loudnorm으로 LUFS 기반 정규화 + true peak 보장.
    TTS 원본(24kHz)을 48kHz로 업샘플링하여 AAC 리샘플링 아티팩트 방지.
    """
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(audio_path),
         "-af", f"aresample=48000,"
                f"loudnorm=I={target_lufs}:TP={true_peak}:LRA=11",
         "-ar", "48000", str(output_path)],
        capture_output=True, check=True,
    )
    return output_path


def get_audio_duration(audio_path: Path) -> float:
    """오디오 파일 길이(초)"""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", str(audio_path)],
        capture_output=True, text=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def build_scene_clip(
    image_path: Path,
    audio_path: Path,
    output_path: Path,
    camera: dict,
    style: dict,
    overlay_path: Path | None = None,
) -> Path:
    """단일 장면 클립 생성 (배경만 줌, 자막 오버레이는 고정)

    apad로 SCENE_GAP만큼 무음 패딩 추가 → 전환 시 나레이션 겹침 방지.
    -shortest 제거 → apad 패딩이 실제로 적용되도록.
    """
    duration = get_audio_duration(audio_path)
    duration += SCENE_GAP  # 무음 갭 (전환용)

    cam_type = camera.get("type", "zoom_in")
    zoom_min, zoom_max = style.get("motion", {}).get("zoom_range", [1.0, 1.25])

    render_fps = 60
    zoompan_vf = _build_camera_filter(cam_type, zoom_min, zoom_max, duration, render_fps)

    if overlay_path and overlay_path.exists():
        # 배경(줌) + 자막 오버레이(고정) 분리 합성
        w, h = VIDEO_WIDTH, VIDEO_HEIGHT
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-framerate", str(render_fps), "-i", str(image_path),
            "-i", str(audio_path),
            "-loop", "1", "-framerate", str(render_fps), "-i", str(overlay_path),
            "-filter_complex",
            f"[0:v]{zoompan_vf}[zoom];"
            f"[2:v]scale={w}:{h},format=rgba[ovr];"
            f"[zoom][ovr]overlay=0:0:format=auto[out];"
            f"[1:a]apad=whole_dur={duration}[aout]",
            "-map", "[out]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-r", str(VIDEO_FPS),
            "-t", str(duration),
            str(output_path),
        ]
    else:
        # 오버레이 없으면 기존 방식
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-framerate", str(render_fps), "-i", str(image_path),
            "-i", str(audio_path),
            "-vf", zoompan_vf,
            "-af", f"apad=whole_dur={duration}",
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-r", str(VIDEO_FPS),
            "-t", str(duration),
            str(output_path),
        ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def build_silent_scene_clip(
    image_path: Path,
    output_path: Path,
    duration: float,
    camera: dict,
    style: dict,
    overlay_path: Path | None = None,
) -> Path:
    """무음 오디오가 붙은 정지/카메라 클립 생성 (시리즈 teaser용)."""
    cam_type = camera.get("type", "static")
    zoom_min, zoom_max = style.get("motion", {}).get("zoom_range", [1.0, 1.25])

    render_fps = 60
    zoompan_vf = _build_camera_filter(cam_type, zoom_min, zoom_max, duration, render_fps)

    if overlay_path and overlay_path.exists():
        w, h = VIDEO_WIDTH, VIDEO_HEIGHT
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-framerate", str(render_fps), "-i", str(image_path),
            "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={duration}",
            "-loop", "1", "-framerate", str(render_fps), "-i", str(overlay_path),
            "-filter_complex",
            f"[0:v]{zoompan_vf}[zoom];"
            f"[2:v]scale={w}:{h},format=rgba[ovr];"
            f"[zoom][ovr]overlay=0:0:format=auto[out]",
            "-map", "[out]", "-map", "1:a",
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-r", str(VIDEO_FPS),
            "-t", str(duration),
            str(output_path),
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-framerate", str(render_fps), "-i", str(image_path),
            "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={duration}",
            "-vf", zoompan_vf,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-r", str(VIDEO_FPS),
            "-t", str(duration),
            str(output_path),
        ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def _build_camera_filter(
    cam_type: str,
    zoom_min: float,
    zoom_max: float,
    duration: float,
    render_fps: int = 60,
) -> str:
    """켄 번즈 효과용 FFmpeg 필터 생성 (부드러운 줌)

    흔들림 방지 3대 원칙:
    1. 고해상도 업스케일 (8000px+) → 1px 반올림 오차 무시
    2. trunc() 좌표 → 반올림 방향 일정
    3. 높은 fps (60) → 프레임당 이동량 감소
    """
    w, h = VIDEO_WIDTH, VIDEO_HEIGHT
    total_frames = int(duration * render_fps)

    # 고해상도 업스케일 (핵심! 1px 반올림 오차를 무시할 수 있게)
    upscale = f"scale=-2:ih*4"

    if cam_type == "zoom_in":
        zoom_expr = f"{zoom_min}+({zoom_max}-{zoom_min})*on/{total_frames}"
        return (
            f"{upscale},"
            f"zoompan=z='{zoom_expr}':"
            f"x='trunc(iw/2-(iw/zoom/2))':"
            f"y='trunc(ih/2-(ih/zoom/2))':"
            f"d={total_frames}:s={w}x{h}:fps={render_fps}"
        )
    elif cam_type == "zoom_out":
        zoom_expr = f"{zoom_max}-({zoom_max}-{zoom_min})*on/{total_frames}"
        return (
            f"{upscale},"
            f"zoompan=z='{zoom_expr}':"
            f"x='trunc(iw/2-(iw/zoom/2))':"
            f"y='trunc(ih/2-(ih/zoom/2))':"
            f"d={total_frames}:s={w}x{h}:fps={render_fps}"
        )
    elif cam_type == "pan_left":
        # zoom_max로 여유 확보 후 오른쪽→왼쪽 패닝
        z = zoom_max
        return (
            f"{upscale},"
            f"zoompan=z='{z}':"
            f"x='trunc((iw-iw/{z})*({total_frames}-on)/{total_frames})':"
            f"y='trunc(ih/2-(ih/zoom/2))':"
            f"d={total_frames}:s={w}x{h}:fps={render_fps}"
        )
    elif cam_type == "pan_right":
        z = zoom_max
        return (
            f"{upscale},"
            f"zoompan=z='{z}':"
            f"x='trunc((iw-iw/{z})*on/{total_frames})':"
            f"y='trunc(ih/2-(ih/zoom/2))':"
            f"d={total_frames}:s={w}x{h}:fps={render_fps}"
        )
    elif cam_type == "pan_up":
        z = zoom_max
        return (
            f"{upscale},"
            f"zoompan=z='{z}':"
            f"x='trunc(iw/2-(iw/zoom/2))':"
            f"y='trunc((ih-ih/{z})*({total_frames}-on)/{total_frames})':"
            f"d={total_frames}:s={w}x{h}:fps={render_fps}"
        )
    else:  # static (zoompan z=1.0으로 프레임 수 제한)
        return (
            f"{upscale},"
            f"zoompan=z='1.0':"
            f"x='trunc(iw/2-(iw/zoom/2))':"
            f"y='trunc(ih/2-(ih/zoom/2))':"
            f"d={total_frames}:s={w}x{h}:fps={render_fps}"
        )


def add_effect_to_clip(
    clip_path: Path,
    effect_path: Path,
    output_path: Path,
    effect_volume: float = 0.7,
) -> Path:
    """클립에 효과음 믹싱"""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(clip_path),
        "-i", str(effect_path),
        "-filter_complex",
        f"[1:a]volume={effect_volume}[fx];"
        f"[0:a][fx]amix=inputs=2:duration=first:normalize=0[out]",
        "-map", "0:v", "-map", "[out]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def concat_with_transitions(
    clips: list[Path],
    output_path: Path,
    transition_types: list[str],
    fade_duration: float = 0.5,
) -> Path:
    """클립들을 전환 효과와 함께 연결 (단일 패스)

    핵심 변경: 순차 xfade(N-1번 AAC 재인코딩) → 단일 filter_complex(1번만 인코딩)
    - 비디오: xfade 체인 (시각 전환 효과 유지)
    - 오디오: atrim + concat (acrossfade 아티팩트 방지, 무음 갭이 전환 역할)
    """
    if len(clips) <= 1:
        if clips:
            import shutil
            shutil.copy2(clips[0], output_path)
        return output_path

    n = len(clips)
    durations = [_get_video_duration(c) for c in clips]

    inputs = []
    for clip in clips:
        inputs.extend(["-i", str(clip)])

    # --- 비디오: xfade 체인 (시각 전환) ---
    video_parts = []
    cumulative = durations[0]

    for i in range(1, n):
        transition = transition_types[i - 1] if i - 1 < len(transition_types) else "fade"
        xfade_type = _map_transition(transition)
        offset = max(0, cumulative - fade_duration)

        src = "[0:v]" if i == 1 else f"[vx{i - 1}]"
        out = f"[vx{i}]" if i < n - 1 else "[vout]"
        video_parts.append(
            f"{src}[{i}:v]xfade=transition={xfade_type}:"
            f"duration={fade_duration}:offset={offset}{out}"
        )
        cumulative = offset + durations[i]

    # --- 오디오: atrim 후 단순 concat ---
    # xfade가 fade_duration만큼 겹치므로 오디오도 각 클립 끝에서 동일하게 제거하여 동기화
    # (각 클립 끝에 SCENE_GAP 무음이 있으므로 제거해도 나레이션 손실 없음)
    audio_parts = []
    for i in range(n):
        if i < n - 1:
            trim_end = max(0, durations[i] - fade_duration)
            audio_parts.append(
                f"[{i}:a]atrim=0:{trim_end},asetpts=PTS-STARTPTS[at{i}]"
            )
        else:
            # 마지막 클립은 트림 없이 그대로
            audio_parts.append(f"[{i}:a]asetpts=PTS-STARTPTS[at{i}]")

    at_labels = "".join(f"[at{i}]" for i in range(n))
    audio_parts.append(f"{at_labels}concat=n={n}:v=0:a=1[aout]")

    # --- 단일 FFmpeg 명령으로 합성 ---
    filter_str = ";".join(video_parts + audio_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_str,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-b:v", "10M", "-maxrate", "12M", "-bufsize", "15M",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # xfade 실패 시 단순 concat 폴백
        _simple_concat(clips, output_path)

    return output_path


def add_bgm(
    video_path: Path,
    bgm_path: Path,
    output_path: Path,
    bgm_volume: float = 0.15,
) -> Path:
    """BGM 레이어 추가 (노멀라이즈 → 볼륨 조절 → 루프 → 페이드)"""
    video_dur = _get_video_duration(video_path)

    # loudnorm으로 BGM을 -16 LUFS로 노멀라이즈 후 bgm_volume 적용
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-stream_loop", "-1", "-i", str(bgm_path),
        "-filter_complex",
        f"[1:a]loudnorm=I=-16:TP=-1.5:LRA=11,"
        f"volume={bgm_volume},"
        f"afade=t=in:d=1,"
        f"afade=t=out:st={max(0, video_dur - 2)}:d=2,"
        f"atrim=0:{video_dur}[bgm];"
        f"[0:a][bgm]amix=inputs=2:duration=first:normalize=0[out]",
        "-map", "0:v", "-map", "[out]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # BGM 믹싱 실패 시 원본 반환
        import shutil
        shutil.copy2(video_path, output_path)
    return output_path


def _get_video_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", str(path)],
        capture_output=True, text=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def _map_transition(transition: str) -> str:
    """스타일 전환 타입 → FFmpeg xfade 타입"""
    mapping = {
        "fade": "fade",
        "slide_left": "slideleft",
        "slide_up": "slideup",
        "zoom": "smoothup",
        "none": "fade",
    }
    return mapping.get(transition, "fade")


def _simple_concat(clips: list[Path], output: Path):
    """단순 concat (전환 효과 없이)"""
    concat_file = output.parent / "_concat_list.txt"
    with open(concat_file, "w") as f:
        for c in clips:
            f.write(f"file '{c}'\n")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
         "-i", str(concat_file), "-c", "copy", str(output)],
        capture_output=True, check=True,
    )
    concat_file.unlink()
