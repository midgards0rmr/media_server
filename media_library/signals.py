import shutil
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from media_library.models import MediaImage, MediaVariant, media_variant_artifact_path


def _delete_storage_file(field_file) -> None:
    if not field_file or not field_file.name:
        return

    storage = field_file.storage
    name = field_file.name

    if storage.exists(name):
        storage.delete(name)


def _delete_empty_parent_dirs(path: Path) -> None:
    media_root = Path(settings.MEDIA_ROOT).resolve()

    for directory in path.parents:
        try:
            resolved = directory.resolve()
        except FileNotFoundError:
            continue

        if resolved == media_root or media_root not in resolved.parents:
            break

        try:
            directory.rmdir()
        except OSError:
            break


def _delete_media_variant_subtitles(variant_pk: int) -> None:
    media_root = Path(settings.MEDIA_ROOT).resolve()
    subtitles_dir = (media_root / "subtitles" / str(variant_pk)).resolve()

    if media_root not in subtitles_dir.parents or not subtitles_dir.exists():
        return

    shutil.rmtree(subtitles_dir)
    _delete_empty_parent_dirs(subtitles_dir)


def _delete_media_variant_hls(variant_pk: int) -> None:
    media_root = Path(settings.MEDIA_ROOT).resolve()
    hls_dir = (media_root / "hls" / str(variant_pk)).resolve()

    if media_root not in hls_dir.parents or not hls_dir.exists():
        return

    shutil.rmtree(hls_dir)
    _delete_empty_parent_dirs(hls_dir)


def _delete_media_variant_artifacts(variant: MediaVariant) -> None:
    media_root = Path(settings.MEDIA_ROOT).resolve()

    for artifact in ("subtitles", "hls", "playable"):
        try:
            artifact_dir = (media_root / media_variant_artifact_path(variant, artifact)).resolve()
        except (AttributeError, ValueError):
            continue

        if media_root not in artifact_dir.parents or not artifact_dir.exists():
            continue

        shutil.rmtree(artifact_dir)
        _delete_empty_parent_dirs(artifact_dir)


@receiver(
    post_delete,
    sender=MediaVariant,
    dispatch_uid="media_library.delete_media_variant_files",
)
def delete_media_variant_files(sender, instance: MediaVariant, **kwargs) -> None:
    file_name = instance.file.name if instance.file else ""
    playable_file_name = instance.playable_file.name if instance.playable_file else ""
    variant_pk = instance.pk

    def cleanup(
        file_name=file_name,
        playable_file_name=playable_file_name,
        variant_pk=variant_pk,
    ):
        if file_name and not MediaVariant.objects.filter(file=file_name).exists():
            _delete_storage_file(instance.file)
            try:
                _delete_empty_parent_dirs(Path(instance.file.path))
            except NotImplementedError:
                pass

        if playable_file_name and not MediaVariant.objects.filter(
            playable_file=playable_file_name
        ).exists():
            _delete_storage_file(instance.playable_file)
            try:
                _delete_empty_parent_dirs(Path(instance.playable_file.path))
            except NotImplementedError:
                pass

        if variant_pk:
            _delete_media_variant_artifacts(instance)
            _delete_media_variant_subtitles(variant_pk)
            _delete_media_variant_hls(variant_pk)

    transaction.on_commit(cleanup)


@receiver(
    post_delete,
    sender=MediaImage,
    dispatch_uid="media_library.delete_media_image_file",
)
def delete_media_image_file(sender, instance: MediaImage, **kwargs) -> None:
    image_name = instance.image.name if instance.image else ""

    def cleanup(image_name=image_name):
        if image_name and not MediaImage.objects.filter(image=image_name).exists():
            _delete_storage_file(instance.image)
            try:
                _delete_empty_parent_dirs(Path(instance.image.path))
            except NotImplementedError:
                pass

    transaction.on_commit(cleanup)
