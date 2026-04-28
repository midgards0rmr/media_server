# Generated manually to replace the flat MediaFile schema with a hierarchical
# title/season/episode/variant structure while the database is still empty.

import django.core.validators
import django.db.models.deletion
import media_library.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("media_library", "0004_mediaimage"),
    ]

    operations = [
        migrations.DeleteModel(
            name="MediaImage",
        ),
        migrations.DeleteModel(
            name="MediaFile",
        ),
        migrations.CreateModel(
            name="MediaTitle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255, verbose_name="Title")),
                ("title_localizations", models.JSONField(blank=True, default=dict, verbose_name="Title localizations")),
                ("original_title", models.CharField(blank=True, max_length=255, verbose_name="Original title")),
                ("slug", models.SlugField(blank=True, max_length=255, unique=True, verbose_name="Slug")),
                ("description", models.TextField(blank=True, verbose_name="Description")),
                ("description_localizations", models.JSONField(blank=True, default=dict, verbose_name="Description localizations")),
                ("media_type", models.CharField(choices=[("movie", "Movie"), ("series", "Series"), ("anime", "Anime"), ("cartoon", "Cartoon"), ("documentary", "Documentary"), ("other", "Other")], default="movie", max_length=20, verbose_name="Media type")),
                ("status", models.CharField(choices=[("announced", "Announced"), ("ongoing", "Ongoing"), ("released", "Released"), ("archived", "Archived")], default="released", max_length=20, verbose_name="Status")),
                ("release_year", models.PositiveSmallIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1888), django.core.validators.MaxValueValidator(2100)], verbose_name="Release year")),
                ("genres", models.JSONField(blank=True, default=list, verbose_name="Genres")),
                ("countries", models.JSONField(blank=True, default=list, verbose_name="Countries")),
                ("language", models.CharField(blank=True, max_length=64, verbose_name="Language")),
                ("age_rating", models.CharField(blank=True, max_length=16, verbose_name="Age rating")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
            ],
            options={
                "verbose_name": "Media title",
                "verbose_name_plural": "Media titles",
                "ordering": ("title",),
                "indexes": [
                    models.Index(fields=["media_type", "status"], name="media_libra_media_t_39857b_idx"),
                    models.Index(fields=["release_year"], name="media_libra_release_a0857b_idx"),
                    models.Index(fields=["title"], name="media_libra_title_3f16cc_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="Season",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("season_number", models.PositiveSmallIntegerField(verbose_name="Season")),
                ("name", models.CharField(blank=True, max_length=255, verbose_name="Season title")),
                ("description", models.TextField(blank=True, verbose_name="Description")),
                ("release_year", models.PositiveSmallIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1888), django.core.validators.MaxValueValidator(2100)], verbose_name="Release year")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                ("title", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="seasons", to="media_library.mediatitle", verbose_name="Media title")),
            ],
            options={
                "verbose_name": "Season",
                "verbose_name_plural": "Seasons",
                "ordering": ("season_number",),
                "constraints": [models.UniqueConstraint(fields=("title", "season_number"), name="unique_title_season")],
            },
        ),
        migrations.CreateModel(
            name="Episode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("episode_number", models.PositiveSmallIntegerField(verbose_name="Episode")),
                ("title", models.CharField(blank=True, max_length=255, verbose_name="Title")),
                ("description", models.TextField(blank=True, verbose_name="Description")),
                ("duration_minutes", models.PositiveIntegerField(blank=True, null=True, verbose_name="Duration (min)")),
                ("release_date", models.DateField(blank=True, null=True, verbose_name="Release date")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                ("season", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="episodes", to="media_library.season", verbose_name="Season")),
            ],
            options={
                "verbose_name": "Episode",
                "verbose_name_plural": "Episodes",
                "ordering": ("episode_number",),
                "constraints": [models.UniqueConstraint(fields=("season", "episode_number"), name="unique_season_episode")],
            },
        ),
        migrations.CreateModel(
            name="MediaVariant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("variant_name", models.CharField(blank=True, max_length=255, verbose_name="Variant name")),
                ("quality", models.CharField(blank=True, max_length=32, verbose_name="Quality")),
                ("video_codec", models.CharField(blank=True, max_length=32, verbose_name="Video codec")),
                ("audio_codec", models.CharField(blank=True, max_length=32, verbose_name="Audio codec")),
                ("audio_tracks", models.JSONField(blank=True, default=list, verbose_name="Audio tracks")),
                ("subtitle_tracks", models.JSONField(blank=True, default=list, verbose_name="Subtitle tracks")),
                ("file", models.FileField(upload_to=media_library.models.media_variant_upload_to, verbose_name="File")),
                ("file_size", models.PositiveBigIntegerField(blank=True, null=True, verbose_name="File size")),
                ("source_path", models.CharField(blank=True, max_length=500, verbose_name="Source path")),
                ("checksum", models.CharField(blank=True, max_length=128, verbose_name="Checksum")),
                ("language", models.CharField(blank=True, max_length=64, verbose_name="Language")),
                ("sort_order", models.PositiveSmallIntegerField(default=0, verbose_name="Sort order")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                ("episode", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="variants", to="media_library.episode", verbose_name="Episode")),
                ("title", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="variants", to="media_library.mediatitle", verbose_name="Media title")),
            ],
            options={
                "verbose_name": "Media variant",
                "verbose_name_plural": "Media variants",
                "ordering": ("sort_order", "id"),
                "indexes": [
                    models.Index(fields=["title"], name="media_libra_title_9281f4_idx"),
                    models.Index(fields=["episode"], name="media_libra_episode_eb6c12_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=(
                            models.Q(title__isnull=False, episode__isnull=True)
                            | models.Q(title__isnull=True, episode__isnull=False)
                        ),
                        name="variant_has_single_parent",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="MediaImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image_type", models.CharField(choices=[("cover", "Cover"), ("poster", "Poster"), ("backdrop", "Backdrop"), ("screenshot", "Screenshot"), ("thumbnail", "Thumbnail"), ("other", "Other")], default="screenshot", max_length=20, verbose_name="Image type")),
                ("image", models.ImageField(upload_to=media_library.models.media_image_upload_to, verbose_name="Image")),
                ("title", models.CharField(blank=True, max_length=255, verbose_name="Title")),
                ("alt_text", models.CharField(blank=True, max_length=255, verbose_name="Alt text")),
                ("caption", models.TextField(blank=True, verbose_name="Caption")),
                ("sort_order", models.PositiveSmallIntegerField(default=0, verbose_name="Sort order")),
                ("is_primary", models.BooleanField(default=False, verbose_name="Is primary")),
                ("width", models.PositiveIntegerField(blank=True, null=True, verbose_name="Width")),
                ("height", models.PositiveIntegerField(blank=True, null=True, verbose_name="Height")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                ("media_title", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="images", to="media_library.mediatitle", verbose_name="Media title")),
            ],
            options={
                "verbose_name": "Media image",
                "verbose_name_plural": "Media images",
                "ordering": ("image_type", "sort_order", "id"),
                "indexes": [
                    models.Index(fields=["media_title", "image_type"], name="media_libra_media_t_90551e_idx"),
                    models.Index(fields=["is_primary"], name="media_libra_is_prim_8b2270_idx"),
                ],
            },
        ),
    ]
