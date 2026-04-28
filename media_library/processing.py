from django.utils import timezone

from media_library.ffmpeg import FFmpegError, analyze_media_variant, generate_hls_variant
from media_library.models import MediaProcessingJob, MediaVariant


def queue_media_processing(variant: MediaVariant) -> MediaProcessingJob:
    return MediaProcessingJob.objects.create(
        variant=variant,
        status=MediaProcessingJob.Status.PENDING,
        stage=MediaProcessingJob.Stage.QUEUED,
        progress=0,
        message="Queued",
    )


def _update_job(
    job: MediaProcessingJob,
    *,
    status: str | None = None,
    stage: str | None = None,
    progress: int | None = None,
    message: str = "",
    error: str = "",
) -> None:
    if status is not None:
        job.status = status
    if stage is not None:
        job.stage = stage
    if progress is not None:
        job.progress = progress
    if message:
        job.message = message
    if error:
        job.error = error

    job.save(
        update_fields=[
            "status",
            "stage",
            "progress",
            "message",
            "error",
            "updated_at",
        ]
    )


def process_media_job(job: MediaProcessingJob) -> None:
    job.status = MediaProcessingJob.Status.RUNNING
    job.stage = MediaProcessingJob.Stage.ANALYZING
    job.progress = 10
    job.message = "Analyzing tracks"
    job.error = ""
    job.started_at = timezone.now()
    job.save(
        update_fields=[
            "status",
            "stage",
            "progress",
            "message",
            "error",
            "started_at",
            "updated_at",
        ]
    )

    try:
        analyze_media_variant(job.variant, extract_subtitles=False)
        _update_job(
            job,
            stage=MediaProcessingJob.Stage.EXTRACTING_SUBTITLES,
            progress=35,
            message="Extracting subtitles",
        )
        analyze_media_variant(job.variant, extract_subtitles=True)
        _update_job(
            job,
            stage=MediaProcessingJob.Stage.GENERATING_HLS,
            progress=60,
            message="Generating HLS",
        )

        def update_hls_progress(progress: int, message: str) -> None:
            _update_job(
                job,
                stage=MediaProcessingJob.Stage.GENERATING_HLS,
                progress=progress,
                message=message,
            )

        generate_hls_variant(job.variant, progress_callback=update_hls_progress)
    except FFmpegError as exc:
        job.status = MediaProcessingJob.Status.FAILED
        job.stage = MediaProcessingJob.Stage.FAILED
        job.progress = 100
        job.message = "Processing failed"
        job.error = str(exc)
        job.finished_at = timezone.now()
        job.save(
            update_fields=[
                "status",
                "stage",
                "progress",
                "message",
                "error",
                "finished_at",
                "updated_at",
            ]
        )
        raise

    job.status = MediaProcessingJob.Status.DONE
    job.stage = MediaProcessingJob.Stage.FINISHED
    job.progress = 100
    job.message = "Ready"
    job.finished_at = timezone.now()
    job.save(
        update_fields=[
            "status",
            "stage",
            "progress",
            "message",
            "finished_at",
            "updated_at",
        ]
    )
