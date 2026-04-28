from django.contrib import admin
from django.contrib import messages
from django.utils.translation import ngettext

from media_library.ffmpeg import (
    FFmpegError,
    analyze_media_variant,
    generate_browser_playable_variant,
    generate_hls_variant,
)

from media_library.models import (
    Episode,
    MediaImage,
    MediaProcessingJob,
    MediaTitle,
    MediaVariant,
    Season,
)


class MediaImageInline(admin.TabularInline):
    model = MediaImage
    extra = 0
    fields = ("image_type", "image", "title", "sort_order", "is_primary")
    ordering = ("image_type", "sort_order", "id")


class SeasonInline(admin.TabularInline):
    model = Season
    extra = 0
    fields = ("season_number", "name", "release_year")
    ordering = ("season_number",)


class EpisodeInline(admin.TabularInline):
    model = Episode
    extra = 0
    fields = ("episode_number", "title", "duration_minutes", "release_date")
    ordering = ("episode_number",)


@admin.register(MediaTitle)
class MediaTitleAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "media_type",
        "status",
        "release_year",
        "updated_at",
    )
    list_filter = ("media_type", "status", "release_year")
    search_fields = ("title", "original_title", "slug")
    readonly_fields = ("slug", "created_at", "updated_at")
    ordering = ("title",)
    inlines = (MediaImageInline, SeasonInline)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "title",
                    "title_localizations",
                    "original_title",
                    "slug",
                    "description",
                    "description_localizations",
                    "media_type",
                    "status",
                )
            },
        ),
        (
            "Release details",
            {
                "fields": (
                    "release_year",
                    "genres",
                    "countries",
                    "language",
                    "age_rating",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
            },
        ),
    )


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ("title", "season_number", "name", "release_year", "updated_at")
    list_filter = ("release_year",)
    search_fields = ("title__title", "title__original_title", "name")
    ordering = ("title", "season_number")
    inlines = (EpisodeInline,)


@admin.register(Episode)
class EpisodeAdmin(admin.ModelAdmin):
    list_display = ("season", "episode_number", "title", "duration_minutes", "updated_at")
    search_fields = ("season__title__title", "title")
    ordering = ("season", "episode_number")


@admin.register(MediaVariant)
class MediaVariantAdmin(admin.ModelAdmin):
    actions = (
        "analyze_tracks",
        "generate_hls_streams",
        "generate_browser_playable_files",
    )
    list_display = (
        "display_parent",
        "variant_name",
        "quality",
        "language",
        "file_size",
        "has_hls",
        "playable_file_size",
        "updated_at",
    )
    search_fields = (
        "title__title",
        "episode__title",
        "episode__season__title__title",
        "variant_name",
        "source_path",
    )
    readonly_fields = (
        "file_size",
        "hls_manifest",
        "hls_error",
        "playable_file_size",
        "playable_error",
        "created_at",
        "updated_at",
    )
    ordering = ("title", "episode", "sort_order", "id")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "title",
                    "episode",
                    "variant_name",
                    "file",
                    "playable_file",
                    "hls_manifest",
                    "source_path",
                    "sort_order",
                )
            },
        ),
        (
            "Technical metadata",
            {
                "fields": (
                    "quality",
                    "video_codec",
                    "audio_codec",
                    "language",
                    "audio_tracks",
                    "subtitle_tracks",
                    "checksum",
                    "file_size",
                    "hls_error",
                    "playable_file_size",
                    "playable_error",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
            },
        ),
    )

    @admin.display(description="Parent")
    def display_parent(self, obj: MediaVariant):
        return obj.title or obj.episode

    @admin.display(boolean=True, description="HLS")
    def has_hls(self, obj: MediaVariant):
        return bool(obj.hls_manifest)

    @admin.action(description="Analyze media tracks")
    def analyze_tracks(self, request, queryset):
        analyzed_count = 0
        failed_count = 0

        for variant in queryset:
            try:
                analyze_media_variant(variant)
            except FFmpegError:
                failed_count += 1
            else:
                analyzed_count += 1

        if analyzed_count:
            self.message_user(
                request,
                ngettext(
                    "%(count)s media file was analyzed.",
                    "%(count)s media files were analyzed.",
                    analyzed_count,
                )
                % {"count": analyzed_count},
                level=messages.SUCCESS,
            )

        if failed_count:
            self.message_user(
                request,
                ngettext(
                    "%(count)s media file could not be analyzed.",
                    "%(count)s media files could not be analyzed.",
                    failed_count,
                )
                % {"count": failed_count},
                level=messages.WARNING,
            )

    @admin.action(description="Generate HLS streams")
    def generate_hls_streams(self, request, queryset):
        generated_count = 0
        failed_count = 0

        for variant in queryset:
            try:
                generate_hls_variant(variant)
            except FFmpegError:
                failed_count += 1
            else:
                generated_count += 1

        if generated_count:
            self.message_user(
                request,
                ngettext(
                    "%(count)s HLS stream was generated.",
                    "%(count)s HLS streams were generated.",
                    generated_count,
                )
                % {"count": generated_count},
                level=messages.SUCCESS,
            )

        if failed_count:
            self.message_user(
                request,
                ngettext(
                    "%(count)s HLS stream could not be generated.",
                    "%(count)s HLS streams could not be generated.",
                    failed_count,
                )
                % {"count": failed_count},
                level=messages.WARNING,
            )

    @admin.action(description="Generate browser playable files")
    def generate_browser_playable_files(self, request, queryset):
        generated_count = 0
        failed_count = 0

        for variant in queryset:
            try:
                generate_browser_playable_variant(variant)
            except FFmpegError:
                failed_count += 1
            else:
                generated_count += 1

        if generated_count:
            self.message_user(
                request,
                ngettext(
                    "%(count)s browser playable file was generated.",
                    "%(count)s browser playable files were generated.",
                    generated_count,
                )
                % {"count": generated_count},
                level=messages.SUCCESS,
            )

        if failed_count:
            self.message_user(
                request,
                ngettext(
                    "%(count)s browser playable file could not be generated.",
                    "%(count)s browser playable files could not be generated.",
                    failed_count,
                )
                % {"count": failed_count},
                level=messages.WARNING,
            )


@admin.register(MediaProcessingJob)
class MediaProcessingJobAdmin(admin.ModelAdmin):
    list_display = (
        "variant",
        "status",
        "stage",
        "progress",
        "created_at",
        "updated_at",
    )
    list_filter = ("status", "stage")
    search_fields = (
        "variant__title__title",
        "variant__episode__title",
        "variant__episode__season__title__title",
        "message",
        "error",
    )
    readonly_fields = (
        "variant",
        "status",
        "stage",
        "progress",
        "message",
        "error",
        "created_at",
        "started_at",
        "finished_at",
        "updated_at",
    )
    ordering = ("-created_at",)


@admin.register(MediaImage)
class MediaImageAdmin(admin.ModelAdmin):
    list_display = (
        "media_title",
        "image_type",
        "title",
        "sort_order",
        "is_primary",
        "updated_at",
    )
    list_filter = ("image_type", "is_primary")
    search_fields = ("media_title__title", "media_title__original_title", "title")
    readonly_fields = ("width", "height", "created_at", "updated_at")
    ordering = ("media_title", "image_type", "sort_order", "id")
