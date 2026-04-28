import json
import subprocess
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.utils.text import slugify

from media_library.models import MediaVariant, media_variant_artifact_path


TEXT_SUBTITLE_CODECS = {"ass", "ssa", "subrip", "mov_text", "webvtt"}
BROWSER_AUDIO_CODECS = {"aac", "mp3", "opus", "vorbis", "flac"}
BROWSER_VIDEO_CODECS = {"h264", "vp8", "vp9", "av1"}
PLAYABLE_CONTAINER_EXTENSIONS = {".mp4", ".m4v"}
LANGUAGE_CODE_MAP = {
    "eng": "en",
    "rus": "ru",
    "jpn": "ja",
    "kor": "ko",
    "chi": "zh",
    "zho": "zh",
    "ger": "de",
    "deu": "de",
    "fre": "fr",
    "fra": "fr",
    "spa": "es",
    "ita": "it",
    "por": "pt",
}


class FFmpegError(RuntimeError):
    pass


def _run_command(command: list[str], timeout: int) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            check=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise FFmpegError(f"Command not found: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise FFmpegError(message) from exc
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError(f"Command timed out: {command[0]}") from exc


def _run_ffmpeg_with_progress(
    command: list[str],
    *,
    timeout: int,
    duration_seconds: float,
    progress_start: int,
    progress_end: int,
    progress_callback=None,
    message: str = "",
) -> None:
    progress_command = [
        *command[:-1],
        "-v",
        "error",
        "-progress",
        "pipe:1",
        "-nostats",
        command[-1],
    ]

    try:
        process = subprocess.Popen(
            progress_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except FileNotFoundError as exc:
        raise FFmpegError(f"Command not found: {command[0]}") from exc

    output_lines = []

    try:
        for line in process.stdout or []:
            line = line.strip()
            if line:
                output_lines.append(line)

            key, _, value = line.partition("=")
            if key not in {"out_time_ms", "out_time_us"} or not value.isdigit():
                continue

            if not duration_seconds:
                continue

            current_seconds = int(value) / 1_000_000
            ratio = min(max(current_seconds / duration_seconds, 0), 1)
            progress = progress_start + int((progress_end - progress_start) * ratio)

            if progress_callback:
                progress_callback(progress, message)

        return_code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        raise FFmpegError(f"Command timed out: {command[0]}") from exc

    if return_code:
        tail = "\n".join(output_lines[-20:])
        raise FFmpegError(tail or f"Command failed: {command[0]}")


def probe_media(path: str) -> dict:
    result = _run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            path,
        ],
        timeout=60,
    )
    return json.loads(result.stdout)


def _stream_title(stream: dict, fallback: str) -> str:
    tags = stream.get("tags") or {}
    return tags.get("title") or tags.get("handler_name") or fallback


def _stream_language(stream: dict) -> str:
    tags = stream.get("tags") or {}
    return tags.get("language") or "und"


def _browser_language_code(language: str) -> str:
    return LANGUAGE_CODE_MAP.get(language, language)


def _is_default(stream: dict) -> bool:
    disposition = stream.get("disposition") or {}
    return bool(disposition.get("default"))


def _subtitle_output_path(variant: MediaVariant, stream_index: int) -> Path:
    return (
        Path(settings.MEDIA_ROOT)
        / media_variant_artifact_path(variant, "subtitles")
        / f"stream_{stream_index}.vtt"
    )


def _subtitle_output_url(variant: MediaVariant, stream_index: int) -> str:
    path = media_variant_artifact_path(variant, "subtitles") / f"stream_{stream_index}.vtt"
    return f"{settings.MEDIA_URL}{path.as_posix()}"


def _extract_subtitle(path: str, variant: MediaVariant, stream_index: int) -> str:
    output_path = _subtitle_output_path(variant, stream_index)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    _run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            path,
            "-map",
            f"0:{stream_index}",
            "-c:s",
            "webvtt",
            str(output_path),
        ],
        timeout=300,
    )
    return _subtitle_output_url(variant, stream_index)


def _browser_playable_output_path(variant: MediaVariant) -> Path:
    source_path = Path(variant.file.path)
    source_stem = slugify(source_path.stem) or f"variant-{variant.pk}"
    return (
        Path(settings.MEDIA_ROOT)
        / media_variant_artifact_path(variant, "playable")
        / f"{source_stem}-browser.mp4"
    )


def _hls_output_dir(variant: MediaVariant) -> Path:
    return Path(settings.MEDIA_ROOT) / media_variant_artifact_path(variant, "hls")


def _hls_manifest_url(variant: MediaVariant) -> str:
    path = media_variant_artifact_path(variant, "hls") / "master.m3u8"
    return f"{settings.MEDIA_URL}{path.as_posix()}"


def _first_video_codec(data: dict) -> str:
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            return stream.get("codec_name") or ""
    return ""


def _first_video_stream(data: dict) -> dict:
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            return stream
    return {}


def _audio_streams(data: dict) -> list[dict]:
    return [
        stream
        for stream in data.get("streams", [])
        if stream.get("codec_type") == "audio"
    ]


def _selected_audio_stream(data: dict, audio_stream_index: int | None = None) -> dict | None:
    audio_streams = _audio_streams(data)
    if not audio_streams:
        return None

    if audio_stream_index is not None:
        for stream in audio_streams:
            if stream.get("index") == audio_stream_index:
                return stream

    for stream in audio_streams:
        if _is_default(stream):
            return stream

    return audio_streams[0]


def _media_duration_seconds(data: dict) -> float:
    try:
        return float((data.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError):
        return 0


def _stream_duration_seconds(stream: dict, fallback: float) -> float:
    try:
        return float(stream.get("duration") or 0) or fallback
    except (TypeError, ValueError):
        return fallback


def needs_browser_playable(variant: MediaVariant) -> bool:
    if variant.playable_file:
        return False

    data = probe_media(variant.file.path)
    video_codec = _first_video_codec(data)
    audio_stream = _selected_audio_stream(data)
    audio_codec = audio_stream.get("codec_name") if audio_stream else ""
    extension = Path(variant.file.name).suffix.lower()

    return (
        extension not in PLAYABLE_CONTAINER_EXTENSIONS
        or video_codec not in BROWSER_VIDEO_CODECS
        or audio_codec not in BROWSER_AUDIO_CODECS
    )


def generate_browser_playable_variant(
    variant: MediaVariant,
    audio_stream_index: int | None = None,
) -> None:
    if not variant.file:
        return

    source_path = variant.file.path
    data = probe_media(source_path)
    video_codec = _first_video_codec(data)
    audio_stream = _selected_audio_stream(data, audio_stream_index=audio_stream_index)
    output_path = _browser_playable_output_path(variant)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    video_codec_args = ["-c:v", "copy"]
    if video_codec not in BROWSER_VIDEO_CODECS:
        video_codec_args = [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
        ]

    command = [
        "ffmpeg",
        "-y",
        "-i",
        source_path,
        "-map",
        "0:v:0",
    ]

    if audio_stream is not None:
        command.extend(["-map", f"0:{audio_stream['index']}"])
    else:
        command.append("-an")

    command.extend(
        [
            *video_codec_args,
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )

    try:
        _run_command(command, timeout=60 * 60 * 6)
    except FFmpegError as exc:
        variant.playable_error = str(exc)
        variant.save(update_fields=["playable_error", "updated_at"])
        raise

    if variant.playable_file:
        variant.playable_file.delete(save=False)

    with output_path.open("rb") as file:
        variant.playable_file.save(output_path.name, File(file), save=False)

    output_path.unlink(missing_ok=True)
    variant.playable_file_size = variant.playable_file.size
    variant.playable_error = ""
    variant.save(
        update_fields=[
            "playable_file",
            "playable_file_size",
            "playable_error",
            "updated_at",
        ]
    )


def _hls_video_codec_args(video_codec: str) -> list[str]:
    if video_codec == "h264":
        return ["-c:v", "copy"]

    return [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "22",
        "-pix_fmt",
        "yuv420p",
    ]


def _hls_video_codec_string(video_stream: dict) -> str:
    codec = video_stream.get("codec_name") or ""
    mime_codec = video_stream.get("mime_codec_string") or ""

    if codec == "h264":
        return mime_codec or "avc1.640028"

    return "avc1.640028"


def _hls_playlist_name(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _hls_audio_directory_name(position: int, stream: dict) -> str:
    language = _browser_language_code(_stream_language(stream))
    suffix = slugify(language) or "und"
    return f"audio_{position:02d}_{suffix}"


def _delete_original_variant_file(variant: MediaVariant, original_name: str) -> None:
    if not original_name:
        return

    storage = variant.file.storage
    if storage.exists(original_name):
        storage.delete(original_name)

    variant.file.name = ""
    variant.file_size = None
    variant.save(update_fields=["file", "file_size", "updated_at"])


def generate_hls_variant(variant: MediaVariant, progress_callback=None) -> None:
    if not variant.file:
        return

    source_path = variant.file.path
    original_name = variant.file.name
    data = probe_media(source_path)
    video_codec = _first_video_codec(data)
    video_stream = _first_video_stream(data)
    audio_streams = _audio_streams(data)
    media_duration = _media_duration_seconds(data)
    output_dir = _hls_output_dir(variant)
    hls_segment_time = str(getattr(settings, "HLS_SEGMENT_TIME", 12))

    if output_dir.exists():
        for path in sorted(output_dir.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()

    video_dir = output_dir / "video"
    video_dir.mkdir(parents=True, exist_ok=True)

    video_command = [
        "ffmpeg",
        "-y",
        "-i",
        source_path,
        "-map",
        "0:v:0",
        "-an",
        *_hls_video_codec_args(video_codec),
        "-hls_time",
        hls_segment_time,
        "-hls_playlist_type",
        "vod",
        "-hls_flags",
        "independent_segments",
        "-hls_segment_filename",
        str(video_dir / "segment_%05d.ts"),
        str(video_dir / "index.m3u8"),
    ]

    try:
        _run_ffmpeg_with_progress(
            video_command,
            timeout=60 * 60 * 6,
            duration_seconds=media_duration,
            progress_start=60,
            progress_end=70,
            progress_callback=progress_callback,
            message="Generating video HLS stream",
        )
        if progress_callback:
            progress_callback(70, "Video HLS stream generated")

        audio_entries = []
        audio_count = len(audio_streams) or 1
        for position, stream in enumerate(audio_streams, start=1):
            audio_dir_name = _hls_audio_directory_name(position, stream)
            audio_dir = output_dir / audio_dir_name
            audio_dir.mkdir(parents=True, exist_ok=True)
            audio_progress_start = 70 + int(20 * (position - 1) / audio_count)
            audio_progress_end = 70 + int(20 * position / audio_count)

            _run_ffmpeg_with_progress(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    source_path,
                    "-map",
                    f"0:{stream['index']}",
                    "-vn",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-ac",
                    "2",
                    "-hls_time",
                    hls_segment_time,
                    "-hls_playlist_type",
                    "vod",
                    "-hls_segment_filename",
                    str(audio_dir / "segment_%05d.ts"),
                    str(audio_dir / "index.m3u8"),
                ],
                timeout=60 * 60 * 6,
                duration_seconds=_stream_duration_seconds(stream, media_duration),
                progress_start=audio_progress_start,
                progress_end=audio_progress_end,
                progress_callback=progress_callback,
                message=f"Generating audio HLS stream {position}/{audio_count}",
            )
            audio_entries.append((position, stream, audio_dir_name))
            if progress_callback:
                progress = 70 + int(20 * position / audio_count)
                progress_callback(progress, f"Audio HLS stream {position}/{audio_count} generated")
    except FFmpegError as exc:
        variant.hls_error = str(exc)
        variant.save(update_fields=["hls_error", "updated_at"])
        raise

    master_lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
    ]

    for position, stream, audio_dir_name in audio_entries:
        title = _stream_title(stream, f"Audio {position}")
        language = _browser_language_code(_stream_language(stream))
        default = "YES" if _is_default(stream) or position == 1 else "NO"
        master_lines.append(
            "#EXT-X-MEDIA:"
            'TYPE=AUDIO,GROUP-ID="audio",'
            f"NAME={_hls_playlist_name(title)},"
            f"LANGUAGE={_hls_playlist_name(language)},"
            f"DEFAULT={default},AUTOSELECT=YES,"
            f"URI={_hls_playlist_name(f'{audio_dir_name}/index.m3u8')}"
        )

    master_lines.extend(
        [
            "#EXT-X-STREAM-INF:"
            "BANDWIDTH=4000000,"
            f"RESOLUTION={video_stream.get('width', 1920)}x{video_stream.get('height', 1080)},"
            f'CODECS="{_hls_video_codec_string(video_stream)},mp4a.40.2",'
            'AUDIO="audio"',
            "video/index.m3u8",
            "",
        ]
    )
    (output_dir / "master.m3u8").write_text("\n".join(master_lines), encoding="utf-8")

    variant.hls_manifest = _hls_manifest_url(variant)
    variant.hls_error = ""
    variant.save(update_fields=["hls_manifest", "hls_error", "updated_at"])

    if getattr(settings, "DELETE_ORIGINAL_AFTER_HLS", True):
        _delete_original_variant_file(variant, original_name)


def analyze_media_variant(variant: MediaVariant, extract_subtitles: bool = True) -> None:
    if not variant.file:
        return

    path = variant.file.path
    data = probe_media(path)
    streams = data.get("streams", [])
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    subtitle_streams = [
        stream for stream in streams if stream.get("codec_type") == "subtitle"
    ]

    audio_tracks = []
    for position, stream in enumerate(audio_streams, start=1):
        codec = stream.get("codec_name") or ""
        language = _stream_language(stream)
        audio_tracks.append(
            {
                "index": stream.get("index"),
                "position": position,
                "title": _stream_title(stream, f"Audio {position}"),
                "language": language,
                "srclang": _browser_language_code(language),
                "codec": codec,
                "channels": stream.get("channels"),
                "default": _is_default(stream),
                "browser_supported": codec in BROWSER_AUDIO_CODECS,
            }
        )

    subtitle_tracks = []
    default_subtitle_marked = False
    for position, stream in enumerate(subtitle_streams, start=1):
        stream_index = stream.get("index")
        codec = stream.get("codec_name") or ""
        language = _stream_language(stream)
        is_default = _is_default(stream)
        track = {
            "index": stream_index,
            "position": position,
            "title": _stream_title(stream, f"Subtitle {position}"),
            "language": language,
            "srclang": _browser_language_code(language),
            "codec": codec,
            "default": is_default and not default_subtitle_marked,
            "browser_supported": codec in TEXT_SUBTITLE_CODECS,
        }

        if track["default"]:
            default_subtitle_marked = True

        if extract_subtitles and stream_index is not None and codec in TEXT_SUBTITLE_CODECS:
            try:
                track["vtt_url"] = _extract_subtitle(path, variant, stream_index)
            except FFmpegError as exc:
                track["error"] = str(exc)

        subtitle_tracks.append(track)

    first_video = video_streams[0] if video_streams else {}
    first_audio = audio_tracks[0] if audio_tracks else {}
    height = first_video.get("height")

    variant.video_codec = first_video.get("codec_name") or variant.video_codec
    variant.audio_codec = first_audio.get("codec") or variant.audio_codec
    variant.audio_tracks = audio_tracks
    variant.subtitle_tracks = subtitle_tracks

    if height and not variant.quality:
        variant.quality = f"{height}p"

    if first_audio and not variant.language:
        variant.language = first_audio.get("language", "")

    variant.save(
        update_fields=[
            "video_codec",
            "audio_codec",
            "audio_tracks",
            "subtitle_tracks",
            "quality",
            "language",
            "updated_at",
        ]
    )
