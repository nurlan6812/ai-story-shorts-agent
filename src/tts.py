"""Gemini TTS 나레이션 생성 (장면 단위)"""

import subprocess
import time
import wave
import re
from pathlib import Path
from typing import Any
from google import genai
from google.genai import types
from config.settings import (
    GEMINI_API_KEY,
    TTS_SPEED,
    TTS_NARRATOR_VOICE,
    TTS_ENABLE_STYLE_STEERING,
    TTS_MODEL_PRIMARY,
    TTS_MODEL_FALLBACK,
)

client = genai.Client(api_key=GEMINI_API_KEY)

FLASH_TTS_MODEL = "gemini-2.5-flash-preview-tts"
PRO_TTS_MODEL = "gemini-2.5-pro-preview-tts"
QUOTE_PAIRS = [
    ('"', '"'),
    ("'", "'"),
    ("“", "”"),
    ("‘", "’"),
    ("「", "」"),
    ("『", "』"),
]


def _save_wav(output_path: Path, pcm_data: bytes, rate: int = 24000):
    """PCM 데이터를 WAV 파일로 저장"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm_data)


def _extract_retry_seconds(err: str) -> int | None:
    """에러 메시지의 'Please retry in ...' 구문에서 대기 시간을 추출."""
    m = re.search(r"Please retry in ([^.\n]+(?:\.\d+)?s)", err)
    if not m:
        return None

    text = m.group(1)
    h = re.search(r"(\d+)h", text)
    mnt = re.search(r"(\d+)m", text)
    sec = re.search(r"(\d+(?:\.\d+)?)s", text)
    total = 0.0
    if h:
        total += int(h.group(1)) * 3600
    if mnt:
        total += int(mnt.group(1)) * 60
    if sec:
        total += float(sec.group(1))
    if total <= 0:
        return None
    return int(total)


def _resolve_tts_model_candidates() -> list[str]:
    """우선 모델 + 폴백 모델 목록을 구성한다."""
    primary = str(TTS_MODEL_PRIMARY or "").strip() or FLASH_TTS_MODEL
    fallback = str(TTS_MODEL_FALLBACK or "").strip()

    models: list[str] = []
    for m in (primary, fallback):
        if m and m not in models:
            models.append(m)

    if len(models) == 1:
        auto_alt = PRO_TTS_MODEL if models[0] == FLASH_TTS_MODEL else FLASH_TTS_MODEL
        if auto_alt not in models:
            models.append(auto_alt)
    return models


def _build_tts_contents(text: str, delivery_instruction: str | None) -> str:
    """TTS 입력 텍스트 구성 (style 지시는 contents로만 전달)."""
    script = str(text or "").strip()
    if not script:
        return ""

    style_hint = str(delivery_instruction or "").strip()
    if not (TTS_ENABLE_STYLE_STEERING and style_hint):
        return script

    # NOTE: preview TTS 모델에서 non-empty system_instruction 사용 시
    # 500 INTERNAL이 반복 재현되어 style 지시는 contents로 전달한다.
    return (
        "TTS task:\n"
        "- Apply style guidance silently.\n"
        "- Never read instruction text.\n"
        "- Speak only the SCRIPT content.\n"
        "- Articulate Korean syllables, particles, and sentence endings clearly.\n"
        "- Do not swallow short question endings or final vowels.\n\n"
        f"STYLE_GUIDANCE:\n{style_hint}\n\n"
        f"SCRIPT:\n{script}"
    )


def _fixed_narrator_delivery_hint() -> str:
    """Narrator는 장면별 감정 연기 대신 일관된 쇼츠 스토리텔러 톤을 유지한다."""
    return (
        "Speak as a consistent Korean Shorts storyteller. "
        "Keep the tone clear, engaging, and easy to follow across all scenes. "
        "Use natural pacing and light emphasis to support tension or payoff, "
        "but do not act as a character, imitate character voices, or overperform emotion. "
        "Pronounce Korean syllables, particles, and sentence endings fully and clearly."
    )


def _strip_outer_quotes_for_tts(text: str, seg_type: str) -> str:
    script = str(text or "").strip()
    if seg_type != "dialogue" or not script:
        return script

    for left, right in QUOTE_PAIRS:
        if script.startswith(left) and script.endswith(right):
            inner = script[len(left):len(script) - len(right)].strip()
            if inner:
                return inner
    return script


def generate_tts(
    text: str,
    output_path: Path,
    voice_name: str | None = None,
    delivery_instruction: str | None = None,
) -> dict:
    """텍스트를 Gemini TTS로 음성 변환"""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # WAV로 생성 후 저장
    wav_path = output_path.with_suffix(".wav")

    voice = (voice_name or TTS_NARRATOR_VOICE or "").strip() or TTS_NARRATOR_VOICE

    contents = _build_tts_contents(text, delivery_instruction)

    # Gemini TTS 사용: 1차 모델 실패 시 폴백 모델로 자동 전환
    model_candidates = _resolve_tts_model_candidates()
    max_retries = 6
    base_wait = 20  # 20s, 40s, 80s, 160s, 320s...
    response = None
    last_error: Exception | None = None
    daily_quota_errors: list[str] = []

    for model_idx, model_name in enumerate(model_candidates):
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=voice,
                                )
                            ),
                        ),
                    ),
                )
                break
            except Exception as e:
                last_error = e
                err = str(e)
                is_daily_quota = any(
                    key in err
                    for key in [
                        "generate_requests_per_model_per_day",
                        "GenerateRequestsPerDayPerProjectPerModel",
                        "per_model_per_day",
                    ]
                )
                has_next_model = model_idx < len(model_candidates) - 1

                if is_daily_quota:
                    hinted = _extract_retry_seconds(err)
                    if not any(msg.startswith(f"{model_name}:") for msg in daily_quota_errors):
                        if hinted:
                            daily_quota_errors.append(
                                f"{model_name}: 일일 쿼터 초과(약 {hinted}초 후 재시도 가능)"
                            )
                        else:
                            daily_quota_errors.append(f"{model_name}: 일일 쿼터 초과")
                    if has_next_model:
                        next_model = model_candidates[model_idx + 1]
                        print(f"  ↪ TTS 모델 전환: {model_name} -> {next_model} (일일 쿼터)")
                    break

                is_retryable = any(
                    key in err
                    for key in ["429", "500", "503", "INTERNAL", "RESOURCE_EXHAUSTED", "UNAVAILABLE"]
                )
                if is_retryable and attempt < max_retries - 1:
                    wait = base_wait * (2 ** attempt)
                    wait = min(wait, 1800)
                    hinted = _extract_retry_seconds(err)
                    if hinted:
                        wait = max(wait, min(hinted, 1800))
                    print(
                        f"  ⏳ Gemini TTS 재시도 대기 {wait}초 "
                        f"({attempt + 1}/{max_retries}, model={model_name})"
                    )
                    time.sleep(wait)
                    continue

                if has_next_model:
                    next_model = model_candidates[model_idx + 1]
                    print(f"  ↪ TTS 모델 전환: {model_name} -> {next_model} (오류 폴백)")
                    break
                raise

        if response is not None:
            break

    if response is None:
        if daily_quota_errors and len(daily_quota_errors) == len(model_candidates):
            detail = "; ".join(daily_quota_errors)
            raise RuntimeError(
                "Gemini TTS 일일 쿼터 초과(모든 폴백 모델 소진). "
                f"{detail}"
            ) from last_error
        if last_error:
            raise last_error
        raise RuntimeError("Gemini TTS 응답이 비어 있습니다.")

    pcm_data = response.candidates[0].content.parts[0].inline_data.data
    _save_wav(wav_path, pcm_data)

    # 배속 적용
    if TTS_SPEED and TTS_SPEED != 1.0:
        sped_path = wav_path.with_stem(wav_path.stem + "_sped")
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(wav_path),
             "-filter:a", f"atempo={TTS_SPEED}",
             str(sped_path)],
            capture_output=True, check=True,
        )
        sped_path.replace(wav_path)

    return {
        "audio_path": str(wav_path),
    }


def _concat_wavs(inputs: list[Path], output_path: Path) -> Path:
    """여러 WAV를 순서대로 이어붙인다."""
    if not inputs:
        raise ValueError("concat inputs is empty")
    if len(inputs) == 1:
        src = inputs[0]
        if src != output_path:
            output_path.write_bytes(src.read_bytes())
        return output_path

    def _escape_ffconcat_path(p: Path) -> str:
        return str(p.resolve()).replace("'", "'\\''")

    list_path = output_path.with_suffix(".txt")
    lines = [f"file '{_escape_ffconcat_path(p)}'" for p in inputs]
    list_path.write_text("\n".join(lines), encoding="utf-8")

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path.resolve()),
                "-c",
                "copy",
                str(output_path.resolve()),
            ],
            capture_output=True,
            check=True,
        )
    finally:
        list_path.unlink(missing_ok=True)
    return output_path


def _normalize_speech_segments(raw: Any) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        out.append(
            {
                "type": str(item.get("type", "narration")).strip() or "narration",
                "speaker": str(item.get("speaker", "narrator")).strip() or "narrator",
                "voice_profile": str(item.get("voice_profile", "")).strip(),
                "text": text,
                "delivery_hint": str(item.get("delivery_hint", "")).strip(),
            }
        )
    return out


def generate_scene_tts(
    scenes: list[dict],
    output_dir: Path,
    voice_map: dict[str, str] | None = None,
) -> list[dict]:
    """모든 장면의 TTS를 순차 생성"""
    output_dir.mkdir(parents=True, exist_ok=True)

    vm = voice_map if isinstance(voice_map, dict) else {}
    results = []
    for i, scene in enumerate(scenes):
        wav_path = output_dir / f"scene_{i:02d}.wav"
        if wav_path.exists():
            wav_path.unlink()

        segments = _normalize_speech_segments((scene or {}).get("speech_segments"))
        segment_meta = []

        if segments:
            partial_wavs: list[Path] = []
            for j, seg in enumerate(segments):
                seg_path = output_dir / f"scene_{i:02d}_seg_{j:02d}.wav"
                if seg_path.exists():
                    seg_path.unlink()
                speaker = seg["speaker"]
                voice = str(vm.get(speaker, vm.get("narrator", TTS_NARRATOR_VOICE))).strip() or TTS_NARRATOR_VOICE
                delivery_hint = str(seg.get("delivery_hint", "")).strip()
                if speaker == "narrator":
                    delivery_hint = _fixed_narrator_delivery_hint()
                tts_text = _strip_outer_quotes_for_tts(seg["text"], seg["type"])
                try:
                    tts_result = generate_tts(
                        tts_text,
                        seg_path,
                        voice_name=voice,
                        delivery_instruction=delivery_hint,
                    )
                except Exception:
                    if voice != TTS_NARRATOR_VOICE:
                        voice = TTS_NARRATOR_VOICE
                        tts_result = generate_tts(
                            tts_text,
                            seg_path,
                            voice_name=voice,
                            delivery_instruction=delivery_hint,
                        )
                    else:
                        raise
                partial_wavs.append(Path(tts_result["audio_path"]))
                segment_meta.append(
                    {
                        "index": j,
                        "speaker": speaker,
                        "voice": voice,
                        "voice_profile": str(seg.get("voice_profile", "")).strip(),
                        "type": seg["type"],
                        "text": seg["text"],
                    }
                )
                # 분당 제한 완화: 호출 간 7초 텀
                if not (i == len(scenes) - 1 and j == len(segments) - 1):
                    time.sleep(7)

            _concat_wavs(partial_wavs, wav_path)
            for p in partial_wavs:
                if p != wav_path:
                    p.unlink(missing_ok=True)
            results.append(
                {
                    "scene_index": i,
                    "audio_path": str(wav_path),
                    "segments": segment_meta,
                }
            )
        else:
            narration = str((scene or {}).get("narration", "")).strip()
            narrator_voice = str(vm.get("narrator", TTS_NARRATOR_VOICE)).strip() or TTS_NARRATOR_VOICE
            tts_result = generate_tts(
                narration,
                wav_path,
                voice_name=narrator_voice,
                delivery_instruction=(
                    "Speak in natural Korean narration style. "
                    "Clear pacing, conversational tone, no exaggerated acting."
                ),
            )
            results.append({"scene_index": i, **tts_result})
            if i < len(scenes) - 1:
                time.sleep(7)

    return results


def run_tts(
    scenes: list[dict],
    output_dir: Path,
    voice_map: dict[str, str] | None = None,
) -> list[dict]:
    """동기 래퍼"""
    return generate_scene_tts(scenes, output_dir, voice_map=voice_map)


if __name__ == "__main__":
    test_scenes = [
        {"narration": "치타는 지구에서 가장 빠른 동물입니다."},
        {"narration": "최고 시속 120킬로미터로 달릴 수 있죠."},
    ]
    results = run_tts(test_scenes, Path("output/test_tts"))
    for r in results:
        print(f"Scene {r['scene_index']}: {r['audio_path']}")
