import time

from django.core.management.base import BaseCommand

from media_library.ffmpeg import (
    FFmpegError,
    analyze_media_variant,
    generate_browser_playable_variant,
    generate_hls_variant,
)
from media_library.models import MediaProcessingJob, MediaVariant
from media_library.processing import process_media_job


class Command(BaseCommand):
    help = "Analyze media files with ffprobe and extract text subtitles to WebVTT."

    def add_arguments(self, parser):
        parser.add_argument(
            "variant_ids",
            nargs="*",
            type=int,
            help="Specific MediaVariant ids to analyze. If omitted, all variants are analyzed.",
        )
        parser.add_argument(
            "--no-subtitles",
            action="store_true",
            help="Analyze streams without extracting text subtitles to .vtt files.",
        )
        parser.add_argument(
            "--generate-playable",
            action="store_true",
            help="Generate browser playable MP4 files with AAC audio.",
        )
        parser.add_argument(
            "--generate-hls",
            action="store_true",
            help="Generate HLS streams with one video stream and separate AAC audio tracks.",
        )
        parser.add_argument(
            "--process-jobs",
            action="store_true",
            help="Process queued media jobs instead of directly processing variants.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Maximum number of queued jobs to process. 0 means no limit.",
        )
        parser.add_argument(
            "--watch",
            action="store_true",
            help="Keep processing queued jobs until interrupted.",
        )
        parser.add_argument(
            "--sleep",
            type=int,
            default=5,
            help="Seconds to wait between queue checks in --watch mode.",
        )

    def handle(self, *args, **options):
        if options["process_jobs"]:
            if options["watch"]:
                self.watch_jobs(limit=options["limit"], sleep_seconds=options["sleep"])
            else:
                self.process_jobs(limit=options["limit"])
            return

        variant_ids = options["variant_ids"]
        extract_subtitles = not options["no_subtitles"]
        generate_playable = options["generate_playable"]
        generate_hls = options["generate_hls"]
        queryset = MediaVariant.objects.all().order_by("id")

        if variant_ids:
            queryset = queryset.filter(id__in=variant_ids)

        analyzed_count = 0
        generated_count = 0
        generated_hls_count = 0
        failed_count = 0

        for variant in queryset:
            try:
                analyze_media_variant(variant, extract_subtitles=extract_subtitles)
                if generate_hls:
                    generate_hls_variant(variant)
                if generate_playable:
                    generate_browser_playable_variant(variant)
            except FFmpegError as exc:
                failed_count += 1
                self.stderr.write(self.style.WARNING(f"{variant.pk}: {exc}"))
            else:
                analyzed_count += 1
                if generate_hls:
                    generated_hls_count += 1
                if generate_playable:
                    generated_count += 1
                self.stdout.write(self.style.SUCCESS(f"{variant.pk}: analyzed"))

        self.stdout.write(
            self.style.SUCCESS(
                "Done. "
                f"Analyzed: {analyzed_count}. "
                f"Generated HLS: {generated_hls_count}. "
                f"Generated playable: {generated_count}. "
                f"Failed: {failed_count}."
            )
        )

    def process_jobs(self, limit: int = 0):
        queryset = MediaProcessingJob.objects.filter(
            status=MediaProcessingJob.Status.PENDING,
        ).order_by("created_at")

        if limit:
            queryset = queryset[:limit]

        processed_count = 0
        failed_count = 0

        for job in queryset:
            try:
                process_media_job(job)
            except FFmpegError as exc:
                failed_count += 1
                self.stderr.write(self.style.WARNING(f"job {job.pk}: {exc}"))
            else:
                processed_count += 1
                self.stdout.write(self.style.SUCCESS(f"job {job.pk}: done"))

        if processed_count or failed_count:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Done. Processed jobs: {processed_count}. Failed jobs: {failed_count}."
                )
            )

        return processed_count, failed_count

    def watch_jobs(self, limit: int = 0, sleep_seconds: int = 5):
        self.stdout.write(self.style.SUCCESS("Media worker started. Press Ctrl+C to stop."))

        try:
            while True:
                processed_count, failed_count = self.process_jobs(limit=limit)
                if not processed_count and not failed_count:
                    time.sleep(sleep_seconds)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Media worker stopped."))
