from pathlib import Path

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _


MEDIA_LIBRARY_DIR = "library"


def _safe_slug(value: str, fallback: str = "media") -> str:
    return slugify(value) or fallback


def media_title_slug(title: "MediaTitle") -> str:
    return _safe_slug(title.original_title or title.title)


def media_variant_base_path(instance: "MediaVariant") -> Path:
    title = instance.title or instance.episode.season.title
    title_slug = media_title_slug(title)

    if instance.episode_id:
        season_number = instance.episode.season.season_number
        episode_number = instance.episode.episode_number
        return (
            Path(MEDIA_LIBRARY_DIR)
            / title_slug
            / "seasons"
            / f"s{season_number:02d}"
            / "episodes"
            / f"e{episode_number:02d}"
        )

    return Path(MEDIA_LIBRARY_DIR) / title_slug / "feature"


def media_variant_artifact_path(instance: "MediaVariant", artifact: str) -> Path:
    variant_key = f"v{instance.pk:06d}" if instance.pk else _safe_slug(instance.variant_name, "variant")
    return media_variant_base_path(instance) / artifact / variant_key


def media_variant_upload_to(instance: "MediaVariant", filename: str) -> str:
    extension = Path(filename).suffix
    title = instance.title or instance.episode.season.title
    title_slug = slugify(title.original_title or title.title) or "media"

    if instance.episode_id:
        season_number = instance.episode.season.season_number
        episode_number = instance.episode.episode_number
        variant_name = slugify(instance.variant_name) or "variant"
        file_name = (
            f"s{season_number:02d}e{episode_number:02d}-{variant_name}{extension}"
        )
    else:
        year_suffix = f"-{title.release_year}" if title.release_year else ""
        variant_name = (
            f"-{slugify(instance.variant_name)}" if instance.variant_name else ""
        )
        file_name = f"{title_slug}{year_suffix}{variant_name}{extension}"

    return str(media_variant_base_path(instance) / "source" / file_name)


def playable_variant_upload_to(instance: "MediaVariant", filename: str) -> str:
    original_path = Path(media_variant_upload_to(instance, filename))
    return str(
        media_variant_artifact_path(instance, "playable")
        / f"{original_path.stem}-browser.mp4"
    )


def media_file_upload_to(instance, filename: str) -> str:
    extension = Path(filename).suffix
    title_slug = (
        slugify(
            getattr(instance, "original_title", "") or getattr(instance, "title", "")
        )
        or "media"
    )

    if getattr(instance, "episode_number", None):
        season_number = getattr(instance, "season_number", 1) or 1
        episode_number = instance.episode_number
        package = f"season_{season_number:02d}"
        file_name = f"s{season_number:02d}e{episode_number:02d}{extension}"
    elif getattr(instance, "season_number", None):
        season_number = instance.season_number
        package = f"season_{season_number:02d}"
        file_name = f"{title_slug}-season-{season_number:02d}{extension}"
    else:
        package = "feature"
        release_year = getattr(instance, "release_year", None)
        year_suffix = f"-{release_year}" if release_year else ""
        file_name = f"{title_slug}{year_suffix}{extension}"

    return f"media/{title_slug}/{package}/{file_name}"


def media_image_upload_to(instance: "MediaImage", filename: str) -> str:
    extension = Path(filename).suffix
    title_slug = (
        slugify(instance.media_title.original_title or instance.media_title.title)
        or "media"
    )
    image_kind = instance.image_type or "image"
    order = instance.sort_order or 0
    file_name = f"{image_kind}-{order:02d}{extension}"
    return f"{MEDIA_LIBRARY_DIR}/{title_slug}/images/{image_kind}/{file_name}"


class Genre(models.Model):
    name = models.CharField(_("Name"), max_length=100, unique=True)

    class Meta:
        ordering = ("name",)
        verbose_name = _("Genre")
        verbose_name_plural = _("Genres")

    def __str__(self) -> str:
        return self.name


class MediaTitle(models.Model):
    class MediaType(models.TextChoices):
        MOVIE = "movie", _("Movie")
        SERIES = "series", _("Series")
        ANIME = "anime", _("Anime")
        CARTOON = "cartoon", _("Cartoon")
        DOCUMENTARY = "documentary", _("Documentary")
        OTHER = "other", _("Other")

    class Status(models.TextChoices):
        ANNOUNCED = "announced", _("Announced")
        ONGOING = "ongoing", _("Ongoing")
        RELEASED = "released", _("Released")
        ARCHIVED = "archived", _("Archived")

    title = models.CharField(_("Title"), max_length=255)
    title_localizations = models.JSONField(
        _("Title localizations"),
        default=dict,
        blank=True,
    )
    original_title = models.CharField(_("Original title"), max_length=255, blank=True)
    slug = models.SlugField(_("Slug"), max_length=255, unique=True, blank=True)
    description = models.TextField(_("Description"), blank=True)
    description_localizations = models.JSONField(
        _("Description localizations"),
        default=dict,
        blank=True,
    )
    media_type = models.CharField(
        _("Media type"),
        max_length=20,
        choices=MediaType.choices,
        default=MediaType.MOVIE,
    )
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=Status.choices,
        default=Status.RELEASED,
    )
    release_year = models.PositiveSmallIntegerField(
        _("Release year"),
        blank=True,
        null=True,
        validators=[MinValueValidator(1888), MaxValueValidator(2100)],
    )
    genres = models.ManyToManyField(
        Genre,
        through="MediaTitleGenre",
        related_name="media_titles",
        verbose_name=_("Genres"),
        blank=True,
    )
    countries = models.JSONField(_("Countries"), default=list, blank=True)
    language = models.CharField(_("Language"), max_length=64, blank=True)
    age_rating = models.CharField(_("Age rating"), max_length=16, blank=True)
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated at"), auto_now=True)

    class Meta:
        ordering = ("title",)
        indexes = [
            models.Index(fields=["media_type", "status"]),
            models.Index(fields=["release_year"]),
            models.Index(fields=["title"]),
        ]
        verbose_name = _("Media title")
        verbose_name_plural = _("Media titles")

    def __str__(self) -> str:
        return self.title

    def get_localized_title(
        self, language_code: str, fallback: str | None = None
    ) -> str:
        return self.title_localizations.get(language_code) or fallback or self.title

    def get_localized_description(
        self,
        language_code: str,
        fallback: str | None = None,
    ) -> str:
        return (
            self.description_localizations.get(language_code)
            or fallback
            or self.description
        )

    def get_primary_image(self):
        return self.images.filter(is_primary=True).first() or self.images.first()

    def get_absolute_url(self):
        return reverse("media_library:mediafile_detail", kwargs={"slug": self.slug})

    def get_primary_variant(self):
        return self.variants.order_by("sort_order", "id").first()

    def is_serialized(self) -> bool:
        return self.media_type in {
            self.MediaType.SERIES,
            self.MediaType.ANIME,
            self.MediaType.CARTOON,
        }

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.original_title or self.title)
            slug = base_slug or "media"
            suffix = 1

            while MediaTitle.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                suffix += 1
                slug = f"{base_slug}-{suffix}" if base_slug else f"media-{suffix}"

            self.slug = slug

        super().save(*args, **kwargs)


class MediaTitleGenre(models.Model):
    media_title = models.ForeignKey(
        MediaTitle,
        on_delete=models.CASCADE,
        related_name="genre_links",
        verbose_name=_("Media title"),
    )
    genre = models.ForeignKey(
        Genre,
        on_delete=models.CASCADE,
        related_name="media_title_links",
        verbose_name=_("Genre"),
    )
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)

    class Meta:
        ordering = ("media_title", "genre__name")
        constraints = [
            models.UniqueConstraint(
                fields=["media_title", "genre"],
                name="unique_media_title_genre",
            ),
        ]
        indexes = [
            models.Index(fields=["media_title", "genre"]),
            models.Index(fields=["genre", "media_title"]),
        ]
        verbose_name = _("Media title genre")
        verbose_name_plural = _("Media title genres")

    def __str__(self) -> str:
        return f"{self.media_title} - {self.genre}"


class Season(models.Model):
    title = models.ForeignKey(
        MediaTitle,
        on_delete=models.CASCADE,
        related_name="seasons",
        verbose_name=_("Media title"),
    )
    season_number = models.PositiveSmallIntegerField(_("Season"))
    name = models.CharField(_("Season title"), max_length=255, blank=True)
    description = models.TextField(_("Description"), blank=True)
    release_year = models.PositiveSmallIntegerField(
        _("Release year"),
        blank=True,
        null=True,
        validators=[MinValueValidator(1888), MaxValueValidator(2100)],
    )
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated at"), auto_now=True)

    class Meta:
        ordering = ("season_number",)
        constraints = [
            models.UniqueConstraint(
                fields=["title", "season_number"],
                name="unique_title_season",
            )
        ]
        verbose_name = _("Season")
        verbose_name_plural = _("Seasons")

    def __str__(self) -> str:
        return self.name or f"{self.title} S{self.season_number:02d}"

    def get_absolute_url(self):
        return reverse(
            "media_library:season_detail",
            kwargs={"slug": self.title.slug, "season_number": self.season_number},
        )


class Episode(models.Model):
    season = models.ForeignKey(
        Season,
        on_delete=models.CASCADE,
        related_name="episodes",
        verbose_name=_("Season"),
    )
    episode_number = models.PositiveSmallIntegerField(_("Episode"))
    title = models.CharField(_("Title"), max_length=255, blank=True)
    description = models.TextField(_("Description"), blank=True)
    duration_minutes = models.PositiveIntegerField(
        _("Duration (min)"),
        blank=True,
        null=True,
    )
    release_date = models.DateField(_("Release date"), blank=True, null=True)
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated at"), auto_now=True)

    class Meta:
        ordering = ("episode_number",)
        constraints = [
            models.UniqueConstraint(
                fields=["season", "episode_number"],
                name="unique_season_episode",
            )
        ]
        verbose_name = _("Episode")
        verbose_name_plural = _("Episodes")

    def __str__(self) -> str:
        label = self.title or _("Episode")
        return f"{self.season} E{self.episode_number:02d} {label}".strip()


class MediaVariant(models.Model):
    title = models.ForeignKey(
        MediaTitle,
        on_delete=models.CASCADE,
        related_name="variants",
        verbose_name=_("Media title"),
        blank=True,
        null=True,
    )
    episode = models.ForeignKey(
        Episode,
        on_delete=models.CASCADE,
        related_name="variants",
        verbose_name=_("Episode"),
        blank=True,
        null=True,
    )
    variant_name = models.CharField(_("Variant name"), max_length=255, blank=True)
    quality = models.CharField(_("Quality"), max_length=32, blank=True)
    video_codec = models.CharField(_("Video codec"), max_length=32, blank=True)
    audio_codec = models.CharField(_("Audio codec"), max_length=32, blank=True)
    audio_tracks = models.JSONField(_("Audio tracks"), default=list, blank=True)
    subtitle_tracks = models.JSONField(_("Subtitle tracks"), default=list, blank=True)
    file = models.FileField(_("File"), upload_to=media_variant_upload_to)
    playable_file = models.FileField(
        _("Playable file"),
        upload_to=playable_variant_upload_to,
        blank=True,
    )
    file_size = models.PositiveBigIntegerField(_("File size"), blank=True, null=True)
    playable_file_size = models.PositiveBigIntegerField(
        _("Playable file size"),
        blank=True,
        null=True,
    )
    playable_error = models.TextField(_("Playable error"), blank=True)
    hls_manifest = models.CharField(_("HLS manifest"), max_length=500, blank=True)
    hls_error = models.TextField(_("HLS error"), blank=True)
    source_path = models.CharField(_("Source path"), max_length=500, blank=True)
    checksum = models.CharField(_("Checksum"), max_length=128, blank=True)
    language = models.CharField(_("Language"), max_length=64, blank=True)
    sort_order = models.PositiveSmallIntegerField(_("Sort order"), default=0)
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated at"), auto_now=True)

    class Meta:
        ordering = ("sort_order", "id")
        indexes = [
            models.Index(fields=["title"]),
            models.Index(fields=["episode"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    (Q(title__isnull=False) & Q(episode__isnull=True))
                    | (Q(title__isnull=True) & Q(episode__isnull=False))
                ),
                name="variant_has_single_parent",
            )
        ]
        verbose_name = _("Media variant")
        verbose_name_plural = _("Media variants")

    def __str__(self) -> str:
        parent = self.title or self.episode
        suffix = f" [{self.variant_name}]" if self.variant_name else ""
        return f"{parent}{suffix}"

    def save(self, *args, **kwargs):
        if self.file and not self.file_size:
            self.file_size = self.file.size
        if self.playable_file and not self.playable_file_size:
            self.playable_file_size = self.playable_file.size
        super().save(*args, **kwargs)


class MediaProcessingJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        RUNNING = "running", _("Running")
        DONE = "done", _("Done")
        FAILED = "failed", _("Failed")

    class Stage(models.TextChoices):
        QUEUED = "queued", _("Queued")
        ANALYZING = "analyzing", _("Analyzing tracks")
        EXTRACTING_SUBTITLES = "extracting_subtitles", _("Extracting subtitles")
        GENERATING_HLS = "generating_hls", _("Generating HLS")
        FINISHED = "finished", _("Finished")
        FAILED = "failed", _("Failed")

    variant = models.ForeignKey(
        MediaVariant,
        on_delete=models.CASCADE,
        related_name="processing_jobs",
        verbose_name=_("Media variant"),
    )
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    stage = models.CharField(
        _("Stage"),
        max_length=40,
        choices=Stage.choices,
        default=Stage.QUEUED,
    )
    progress = models.PositiveSmallIntegerField(
        _("Progress"),
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    message = models.CharField(_("Message"), max_length=255, blank=True)
    error = models.TextField(_("Error"), blank=True)
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)
    started_at = models.DateTimeField(_("Started at"), blank=True, null=True)
    finished_at = models.DateTimeField(_("Finished at"), blank=True, null=True)
    updated_at = models.DateTimeField(_("Updated at"), auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["variant", "status"]),
        ]
        verbose_name = _("Media processing job")
        verbose_name_plural = _("Media processing jobs")

    def __str__(self) -> str:
        return f"{self.variant} [{self.get_status_display()}]"


class MediaImage(models.Model):
    class ImageType(models.TextChoices):
        COVER = "cover", _("Cover")
        POSTER = "poster", _("Poster")
        BACKDROP = "backdrop", _("Backdrop")
        SCREENSHOT = "screenshot", _("Screenshot")
        THUMBNAIL = "thumbnail", _("Thumbnail")
        OTHER = "other", _("Other")

    media_title = models.ForeignKey(
        MediaTitle,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name=_("Media title"),
    )
    image_type = models.CharField(
        _("Image type"),
        max_length=20,
        choices=ImageType.choices,
        default=ImageType.SCREENSHOT,
    )
    image = models.ImageField(_("Image"), upload_to=media_image_upload_to)
    title = models.CharField(_("Title"), max_length=255, blank=True)
    alt_text = models.CharField(_("Alt text"), max_length=255, blank=True)
    caption = models.TextField(_("Caption"), blank=True)
    sort_order = models.PositiveSmallIntegerField(_("Sort order"), default=0)
    is_primary = models.BooleanField(_("Is primary"), default=False)
    width = models.PositiveIntegerField(_("Width"), blank=True, null=True)
    height = models.PositiveIntegerField(_("Height"), blank=True, null=True)
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated at"), auto_now=True)

    class Meta:
        ordering = ("image_type", "sort_order", "id")
        indexes = [
            models.Index(fields=["media_title", "image_type"]),
            models.Index(fields=["is_primary"]),
        ]
        verbose_name = _("Media image")
        verbose_name_plural = _("Media images")

    def __str__(self) -> str:
        return self.title or f"{self.media_title} [{self.get_image_type_display()}]"

    def save(self, *args, **kwargs):
        if self.image:
            self.width = self.image.width
            self.height = self.image.height
        super().save(*args, **kwargs)
