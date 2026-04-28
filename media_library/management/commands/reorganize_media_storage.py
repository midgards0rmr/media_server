import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from media_library.models import (
    MediaImage,
    MediaVariant,
    media_image_upload_to,
    media_variant_artifact_path,
    media_variant_upload_to,
    playable_variant_upload_to,
)


class Command(BaseCommand):
    help = "Move media files to the library/<title>/... storage layout."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually move files and update database records.",
        )

    def handle(self, *args, **options):
        self.apply = options["apply"]
        self.media_root = Path(settings.MEDIA_ROOT).resolve()
        self.moved = 0
        self.updated = 0

        self.stdout.write(
            self.style.WARNING("Dry run. Pass --apply to move files.")
            if not self.apply
            else self.style.WARNING("Applying media storage reorganization.")
        )

        for image in MediaImage.objects.select_related("media_title"):
            self._move_image(image)

        for variant in (
            MediaVariant.objects.select_related("title", "episode__season__title")
            .prefetch_related("processing_jobs")
            .order_by("pk")
        ):
            self._move_variant_source(variant)
            self._move_variant_playable(variant)
            self._move_variant_hls(variant)
            self._move_variant_subtitles(variant)

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Moved paths: {self.moved}. Updated records: {self.updated}."
            )
        )

    def _absolute(self, relative_name: str) -> Path:
        return (self.media_root / relative_name).resolve()

    def _relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.media_root).as_posix()

    def _unique_target(self, target: Path) -> Path:
        if not target.exists():
            return target

        stem = target.stem
        suffix = target.suffix
        parent = target.parent
        counter = 2

        while True:
            candidate = parent / f"{stem}-{counter}{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

    def _move_path(self, source_name: str, target_name: str) -> str:
        if not source_name or source_name == target_name:
            return source_name

        source = self._absolute(source_name)
        target = self._unique_target(self._absolute(target_name))
        final_name = self._relative(target)

        if not source.exists():
            self.stdout.write(self.style.WARNING(f"Missing: {source_name}"))
            return source_name

        self.stdout.write(f"{source_name} -> {final_name}")

        if self.apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            self._delete_empty_parent_dirs(source.parent)

        self.moved += 1
        return final_name

    def _delete_empty_parent_dirs(self, start: Path) -> None:
        for directory in start.resolve().parents:
            if directory == self.media_root or self.media_root not in directory.parents:
                break

            try:
                directory.rmdir()
            except OSError:
                break

    def _move_image(self, image: MediaImage) -> None:
        if not image.image:
            return

        target_name = media_image_upload_to(image, Path(image.image.name).name)
        new_name = self._move_path(image.image.name, target_name)
        if new_name != image.image.name and self.apply:
            image.image.name = new_name
            image.save(update_fields=["image", "updated_at"])
            self.updated += 1

    def _move_variant_source(self, variant: MediaVariant) -> None:
        if not variant.file:
            return

        target_name = media_variant_upload_to(variant, Path(variant.file.name).name)
        new_name = self._move_path(variant.file.name, target_name)
        if new_name != variant.file.name and self.apply:
            variant.file.name = new_name
            variant.save(update_fields=["file", "updated_at"])
            self.updated += 1

    def _move_variant_playable(self, variant: MediaVariant) -> None:
        if not variant.playable_file:
            return

        target_name = playable_variant_upload_to(
            variant,
            Path(variant.playable_file.name).name,
        )
        new_name = self._move_path(variant.playable_file.name, target_name)
        if new_name != variant.playable_file.name and self.apply:
            variant.playable_file.name = new_name
            variant.save(update_fields=["playable_file", "updated_at"])
            self.updated += 1

    def _move_variant_hls(self, variant: MediaVariant) -> None:
        old_dir = self.media_root / "hls" / str(variant.pk)
        new_dir = self.media_root / media_variant_artifact_path(variant, "hls")
        new_manifest_url = (
            f"{settings.MEDIA_URL}"
            f"{(media_variant_artifact_path(variant, 'hls') / 'master.m3u8').as_posix()}"
        )

        if old_dir.exists() and old_dir.resolve() != new_dir.resolve():
            self.stdout.write(f"{self._relative(old_dir)} -> {self._relative(new_dir)}")
            if self.apply:
                new_dir.parent.mkdir(parents=True, exist_ok=True)
                if new_dir.exists():
                    shutil.rmtree(new_dir)
                shutil.move(str(old_dir), str(new_dir))
                self._delete_empty_parent_dirs(old_dir.parent)
            self.moved += 1

        if variant.hls_manifest != new_manifest_url and (
            old_dir.exists() or new_dir.exists() or variant.hls_manifest
        ):
            self.stdout.write(f"HLS URL {variant.pk}: {variant.hls_manifest} -> {new_manifest_url}")
            if self.apply:
                variant.hls_manifest = new_manifest_url
                variant.save(update_fields=["hls_manifest", "updated_at"])
                self.updated += 1

    def _move_variant_subtitles(self, variant: MediaVariant) -> None:
        old_dir = self.media_root / "subtitles" / str(variant.pk)
        new_dir = self.media_root / media_variant_artifact_path(variant, "subtitles")

        if old_dir.exists() and old_dir.resolve() != new_dir.resolve():
            self.stdout.write(f"{self._relative(old_dir)} -> {self._relative(new_dir)}")
            if self.apply:
                new_dir.parent.mkdir(parents=True, exist_ok=True)
                if new_dir.exists():
                    shutil.rmtree(new_dir)
                shutil.move(str(old_dir), str(new_dir))
                self._delete_empty_parent_dirs(old_dir.parent)
            self.moved += 1

        tracks = variant.subtitle_tracks or []
        changed = False
        for track in tracks:
            old_url = track.get("vtt_url")
            if not old_url:
                continue

            filename = Path(old_url).name
            new_url = (
                f"{settings.MEDIA_URL}"
                f"{(media_variant_artifact_path(variant, 'subtitles') / filename).as_posix()}"
            )
            if old_url != new_url:
                track["vtt_url"] = new_url
                changed = True

        if changed:
            self.stdout.write(f"Subtitle URLs {variant.pk}: updated")
            if self.apply:
                variant.subtitle_tracks = tracks
                variant.save(update_fields=["subtitle_tracks", "updated_at"])
                self.updated += 1
