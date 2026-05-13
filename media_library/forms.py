import json

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.template.defaultfilters import filesizeformat
from django.utils.translation import gettext_lazy as _

from media_library.models import Episode, Genre, MediaTitle, MediaVariant, Season


class MediaTitleForm(forms.ModelForm):
    genres = forms.CharField(
        label=_("Genres"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_("Enter a JSON array or one genre per line."),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["genres"].initial = "\n".join(
                self.instance.genres.order_by("name").values_list("name", flat=True)
            )

    def clean_genres(self):
        value = self.cleaned_data.get("genres", "")
        if not value:
            return []

        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = value.replace(",", "\n").splitlines()

        if not isinstance(parsed, list):
            raise ValidationError(_("Genres must be a list."))

        genres = []
        seen = set()
        for item in parsed:
            if not isinstance(item, str):
                raise ValidationError(_("Each genre must be text."))
            genre = item.strip()
            key = genre.casefold()
            if genre and key not in seen:
                seen.add(key)
                genres.append(genre)

        return genres

    def _get_or_create_genre(self, name):
        genre = Genre.objects.filter(name__iexact=name).first()
        if genre:
            return genre
        return Genre.objects.create(name=name)

    def save(self, commit=True):
        genre_names = self.cleaned_data.pop("genres", [])
        instance = super().save(commit=commit)
        if commit:
            genre_objects = [self._get_or_create_genre(name) for name in genre_names]
            instance.genres.set(genre_objects)
        else:
            self._pending_genre_names = genre_names
        return instance

    def save_m2m(self):
        super().save_m2m()
        if hasattr(self, "_pending_genre_names"):
            genre_objects = [
                self._get_or_create_genre(name) for name in self._pending_genre_names
            ]
            self.instance.genres.set(genre_objects)

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
