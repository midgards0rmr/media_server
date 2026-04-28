from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.template.defaultfilters import filesizeformat
from django.utils.translation import gettext_lazy as _

from media_library.models import Episode, MediaTitle, MediaVariant, Season


class MediaTitleForm(forms.ModelForm):
    class Meta:
        model = MediaTitle
        fields = [
            "title",
            "title_localizations",
            "original_title",
            "description",
            "description_localizations",
            "media_type",
            "status",
            "release_year",
            "genres",
            "countries",
            "language",
            "age_rating",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "title_localizations": forms.Textarea(attrs={"rows": 4}),
            "description_localizations": forms.Textarea(attrs={"rows": 4}),
            "genres": forms.Textarea(attrs={"rows": 3}),
            "countries": forms.Textarea(attrs={"rows": 3}),
        }


class SeasonForm(forms.ModelForm):
    class Meta:
        model = Season
        fields = ["season_number", "name", "description", "release_year"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }


class EpisodeForm(forms.ModelForm):
    class Meta:
        model = Episode
        fields = ["episode_number", "title", "description", "duration_minutes", "release_date"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "release_date": forms.DateInput(attrs={"type": "date"}),
        }


class MediaVariantUploadForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        max_size = getattr(settings, "MEDIA_UPLOAD_MAX_SIZE", None)
        if max_size:
            self.fields["file"].help_text = _(
                "Maximum upload size: %(size)s. Large files are stored through a disk temporary directory."
            ) % {"size": filesizeformat(max_size)}

    def clean_file(self):
        file = self.cleaned_data.get("file")
        max_size = getattr(settings, "MEDIA_UPLOAD_MAX_SIZE", None)

        if file and max_size and file.size > max_size:
            raise ValidationError(
                _("File is too large. Maximum allowed size is %(size)s."),
                params={"size": filesizeformat(max_size)},
                code="file_too_large",
            )

        return file

    class Meta:
        model = MediaVariant
        fields = [
            "variant_name",
            "file",
        ]


MediaVariantForm = MediaVariantUploadForm
