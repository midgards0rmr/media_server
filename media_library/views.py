import mimetypes
import os
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Prefetch, Q
from django.http import (
    FileResponse,
    Http404,
    HttpResponse,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import get_object_or_404, redirect
from django.template.defaultfilters import filesizeformat
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext as _
from django.utils.translation import get_language
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from media_library.forms import EpisodeForm, MediaTitleForm, MediaVariantForm, SeasonForm
from media_library.models import (
    Episode,
    MediaImage,
    MediaProcessingJob,
    MediaTitle,
    MediaVariant,
    Season,
)
from media_library.processing import queue_media_processing
from media_library.tmdb import TMDBClient, TMDBError, download_tmdb_image


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = reverse_lazy("admin:login")

    def test_func(self):
        return self.request.user.is_staff


class StaffJSONView(StaffRequiredMixin, View):
    def render_json(self, payload: dict, status: int = 200) -> JsonResponse:
        return JsonResponse(payload, status=status)


class UploadSizeLimitMixin:
    def dispatch(self, request, *args, **kwargs):
        max_size = getattr(settings, "MEDIA_UPLOAD_MAX_SIZE", None)
        content_length = request.META.get("CONTENT_LENGTH")

        if request.method == "POST" and max_size and content_length:
            try:
                request_size = int(content_length)
            except ValueError:
                request_size = 0

            if request_size > max_size + getattr(
                settings,
                "DATA_UPLOAD_MAX_MEMORY_SIZE",
                0,
            ):
                message = _("File is too large. Maximum allowed size is %(size)s.") % {
                    "size": filesizeformat(max_size),
                }
                return HttpResponse(message, status=413)

        return super().dispatch(request, *args, **kwargs)


def _analyze_variant_metadata(request, variant: MediaVariant) -> None:
    queue_media_processing(variant)
    messages.success(request, _("File was uploaded and queued for processing."))


def _tmdb_enabled() -> bool:
    return bool(
        getattr(settings, "TMDB_READ_ACCESS_TOKEN", "")
        or getattr(settings, "TMDB_API_KEY", "")
        or getattr(settings, "TMDB_API_TOKEN", "")
    )


def _parse_range_header(range_header: str, file_size: int) -> tuple[int, int] | None:
    if not range_header.startswith("bytes="):
        return None

    ranges = range_header.removeprefix("bytes=").split(",")
    if len(ranges) != 1:
        return None

    start_text, _, end_text = ranges[0].strip().partition("-")
    if not start_text and not end_text:
        return None

    try:
        if start_text:
            start = int(start_text)
            end = int(end_text) if end_text else file_size - 1
        else:
            suffix_length = int(end_text)
            if suffix_length <= 0:
                return None
            start = max(file_size - suffix_length, 0)
            end = file_size - 1
    except ValueError:
        return None

    if start < 0 or end < start or start >= file_size:
        return None

    return start, min(end, file_size - 1)


def _file_chunk_iterator(
    path: str,
    start: int,
    length: int,
    chunk_size: int = 1024 * 1024,
):
    with open(path, "rb") as file:
        file.seek(start)
        remaining = length

        while remaining > 0:
            chunk = file.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


class MediaVariantStreamView(View):
    def get(self, request, pk):
        variant = get_object_or_404(MediaVariant, pk=pk)
        stream_file = variant.playable_file or variant.file
        if not stream_file:
            if variant.hls_manifest:
                return redirect(variant.hls_manifest)
            raise Http404(_("File not found."))

        path = stream_file.path
        if not os.path.exists(path):
            raise Http404(_("File not found."))

        file_size = os.path.getsize(path)
        content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
        filename = quote(os.path.basename(path))
        range_header = request.headers.get("Range", "").strip()

        if range_header:
            byte_range = _parse_range_header(range_header, file_size)
            if byte_range is None:
                response = HttpResponse(status=416)
                response["Content-Range"] = f"bytes */{file_size}"
                response["Accept-Ranges"] = "bytes"
                return response

            start, end = byte_range
            content_length = end - start + 1
            response = StreamingHttpResponse(
                _file_chunk_iterator(path, start, content_length),
                status=206,
                content_type=content_type,
            )
            response["Content-Range"] = f"bytes {start}-{end}/{file_size}"
            response["Content-Length"] = str(content_length)
        else:
            response = FileResponse(open(path, "rb"), content_type=content_type)
            response["Content-Length"] = str(file_size)

        response["Accept-Ranges"] = "bytes"
        response["Content-Disposition"] = f"inline; filename*=UTF-8''{filename}"
        return response


class HLSMediaView(View):
    content_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".m3u8": "application/vnd.apple.mpegurl",
        ".ts": "video/mp2t",
        ".vtt": "text/vtt",
    }

    def get(self, request, path, root="hls"):
        media_root = Path(settings.MEDIA_ROOT).resolve()
        asset_root = (media_root / root).resolve()
        file_path = (asset_root / path).resolve()

        if asset_root not in file_path.parents or not file_path.exists():
            raise Http404(_("File not found."))

        content_type = self.content_types.get(
            file_path.suffix.lower(),
            "application/octet-stream",
        )
        response = FileResponse(file_path.open("rb"), content_type=content_type)
        response["Content-Length"] = str(file_path.stat().st_size)
        return response


class MediaProcessingJobStatusView(StaffJSONView):
    def get(self, request, pk):
        job = get_object_or_404(MediaProcessingJob, pk=pk)
        return self.render_json(
            {
                "id": job.pk,
                "status": job.status,
                "status_display": job.get_status_display(),
                "stage": job.stage,
                "stage_display": job.get_stage_display(),
                "progress": job.progress,
                "message": job.message,
                "error": job.error,
                "updated_at": job.updated_at.isoformat(),
            }
        )


class TMDBImageAttachMixin:
    def _attach_tmdb_images(self, media_title: MediaTitle) -> None:
        poster_url = self.request.POST.get("tmdb_poster_url", "").strip()
        backdrop_url = self.request.POST.get("tmdb_backdrop_url", "").strip()

        if poster_url and not media_title.images.filter(
            image_type=MediaImage.ImageType.POSTER
        ).exists():
            download_tmdb_image(
                media_title,
                poster_url,
                MediaImage.ImageType.POSTER,
            )

        if backdrop_url and not media_title.images.filter(
            image_type=MediaImage.ImageType.BACKDROP
        ).exists():
            download_tmdb_image(
                media_title,
                backdrop_url,
                MediaImage.ImageType.BACKDROP,
            )

    def _tmdb_enabled(self) -> bool:
        return _tmdb_enabled()


class MediaFileListView(ListView):
    model = MediaTitle
    template_name = "media_library/mediafile_list.html"
    context_object_name = "media_files"
    paginate_by = 20

    def _base_queryset(self):
        return (
            super()
            .get_queryset()
            .prefetch_related(
                "images",
                "variants",
                Prefetch("seasons", queryset=Season.objects.prefetch_related("episodes")),
            )
        )

    def _available_genres(self):
        genres = set()
        for genre_list in self._base_queryset().values_list("genres", flat=True):
            if isinstance(genre_list, list):
                genres.update(
                    genre.strip()
                    for genre in genre_list
                    if isinstance(genre, str) and genre.strip()
                )
        return sorted(genres, key=str.lower)

    def _available_years(self):
        years = self._base_queryset().exclude(release_year__isnull=True).values_list(
            "release_year",
            flat=True,
        )
        return sorted(set(years), reverse=True)

    def get_queryset(self):
        queryset = self._base_queryset().order_by("title")
        query = self.request.GET.get("q", "").strip()
        media_type = self.request.GET.get("type", "").strip()
        year = self.request.GET.get("year", "").strip()
        selected_genres = [
            genre.strip() for genre in self.request.GET.getlist("genres") if genre.strip()
        ]

        if query:
            queryset = queryset.filter(
                Q(title__icontains=query)
                | Q(original_title__icontains=query)
                | Q(title_localizations__icontains=query)
                | Q(description__icontains=query)
                | Q(description_localizations__icontains=query)
                | Q(seasons__episodes__title__icontains=query)
            ).distinct()

        if media_type:
            queryset = queryset.filter(media_type=media_type)

        if year:
            queryset = queryset.filter(release_year=year)

        for genre in selected_genres:
            queryset = queryset.filter(genres__contains=[genre])

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "").strip()
        context["selected_type"] = self.request.GET.get("type", "").strip()
        context["selected_year"] = self.request.GET.get("year", "").strip()
        context["selected_genres"] = self.request.GET.getlist("genres")
        context["media_types"] = MediaTitle.MediaType.choices
        context["available_years"] = self._available_years()
        context["available_genres"] = self._available_genres()
        context["media_count"] = self.get_queryset().count()
        return context


class MediaFileDetailView(DetailView):
    model = MediaTitle
    template_name = "media_library/mediafile_detail.html"
    context_object_name = "media_file"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .prefetch_related(
                "images",
                Prefetch(
                    "variants",
                    queryset=MediaVariant.objects.prefetch_related("processing_jobs"),
                ),
                Prefetch(
                    "seasons",
                    queryset=Season.objects.prefetch_related(
                        Prefetch(
                            "episodes",
                            queryset=Episode.objects.prefetch_related("variants"),
                        )
                    ),
                ),
            )
        )


class SeasonDetailView(DetailView):
    model = Season
    template_name = "media_library/season_detail.html"
    context_object_name = "season"

    def get_queryset(self):
        return Season.objects.select_related("title").prefetch_related(
            Prefetch(
                "episodes",
                queryset=Episode.objects.prefetch_related(
                    Prefetch(
                        "variants",
                        queryset=MediaVariant.objects.prefetch_related("processing_jobs"),
                    )
                ),
            )
        )

    def get_object(self, queryset=None):
        queryset = self.get_queryset()
        return queryset.get(
            title__slug=self.kwargs["slug"],
            season_number=self.kwargs["season_number"],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        episodes = list(self.object.episodes.all())
        requested_episode = self.request.GET.get("episode", "")
        active_episode = None

        if requested_episode.isdigit():
            active_episode = next(
                (
                    episode
                    for episode in episodes
                    if episode.episode_number == int(requested_episode)
                ),
                None,
            )

        if active_episode is None:
            active_episode = next(
                (episode for episode in episodes if episode.variants.all()),
                episodes[0] if episodes else None,
            )

        active_variant = None
        if active_episode is not None:
            variants = list(active_episode.variants.all())
            active_variant = next(
                (
                    variant
                    for variant in variants
                    if variant.hls_manifest
                    or variant.subtitle_tracks
                    or variant.audio_tracks
                    or variant.playable_file
                ),
                variants[0] if variants else None,
            )

        context["active_episode"] = active_episode
        context["active_variant"] = active_variant
        return context


class MediaFileCreateView(TMDBImageAttachMixin, StaffRequiredMixin, CreateView):
    model = MediaTitle
    form_class = MediaTitleForm
    template_name = "media_library/mediafile_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tmdb_enabled"] = _tmdb_enabled()
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        self._attach_tmdb_images(self.object)
        return response


class MediaFileUpdateView(TMDBImageAttachMixin, StaffRequiredMixin, UpdateView):
    model = MediaTitle
    form_class = MediaTitleForm
    template_name = "media_library/mediafile_form.html"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tmdb_enabled"] = _tmdb_enabled()
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        self._attach_tmdb_images(self.object)
        return response


class MediaFileDeleteView(StaffRequiredMixin, DeleteView):
    model = MediaTitle
    template_name = "media_library/mediafile_confirm_delete.html"
    context_object_name = "media_file"
    success_url = reverse_lazy("media_library:mediafile_list")
    slug_field = "slug"
    slug_url_kwarg = "slug"


class SeasonCreateView(StaffRequiredMixin, CreateView):
    model = Season
    form_class = SeasonForm
    template_name = "media_library/related_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.media_title = get_object_or_404(MediaTitle, slug=kwargs["slug"])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.title = self.media_title
        return super().form_valid(form)

    def get_success_url(self):
        return self.object.get_absolute_url()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("Add season")
        context["parent"] = self.media_title
        context["cancel_url"] = self.media_title.get_absolute_url()
        language = (get_language() or "").split("-")[0]
        context["tmdb_enabled"] = _tmdb_enabled()
        context["season_import"] = True
        context["season_import_query"] = (
            self.media_title.get_localized_title(language)
            or self.media_title.original_title
            or self.media_title.title
        )
        return context


class EpisodeCreateView(StaffRequiredMixin, CreateView):
    model = Episode
    form_class = EpisodeForm
    template_name = "media_library/related_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.season = get_object_or_404(
            Season,
            title__slug=kwargs["slug"],
            season_number=kwargs["season_number"],
        )
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.season = self.season
        return super().form_valid(form)

    def get_success_url(self):
        return self.season.get_absolute_url()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        language = (get_language() or "").split("-")[0]
        context["page_title"] = _("Add episode")
        context["parent"] = self.season
        context["cancel_url"] = self.season.get_absolute_url()
        context["tmdb_enabled"] = _tmdb_enabled()
        context["episode_import"] = True
        context["episode_import_query"] = (
            self.season.title.get_localized_title(language)
            or self.season.title.original_title
            or self.season.title.title
        )
        context["episode_import_season_number"] = self.season.season_number
        return context


class TitleVariantCreateView(UploadSizeLimitMixin, StaffRequiredMixin, CreateView):
    model = MediaVariant
    form_class = MediaVariantForm
    template_name = "media_library/related_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.media_title = get_object_or_404(MediaTitle, slug=kwargs["slug"])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.title = self.media_title
        response = super().form_valid(form)
        _analyze_variant_metadata(self.request, self.object)
        return response

    def get_success_url(self):
        return self.media_title.get_absolute_url()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Добавить файл"
        context["parent"] = self.media_title
        context["cancel_url"] = self.media_title.get_absolute_url()
        return context


class EpisodeVariantCreateView(UploadSizeLimitMixin, StaffRequiredMixin, CreateView):
    model = MediaVariant
    form_class = MediaVariantForm
    template_name = "media_library/related_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.episode = get_object_or_404(
            Episode,
            season__title__slug=kwargs["slug"],
            season__season_number=kwargs["season_number"],
            episode_number=kwargs["episode_number"],
        )
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.episode = self.episode
        response = super().form_valid(form)
        _analyze_variant_metadata(self.request, self.object)
        return response

    def get_success_url(self):
        return self.episode.season.get_absolute_url()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Добавить файл серии"
        context["parent"] = self.episode
        context["cancel_url"] = self.episode.season.get_absolute_url()
        return context


class EpisodeWithVariantCreateView(UploadSizeLimitMixin, StaffRequiredMixin, View):
    template_name = "media_library/episode_with_variant_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.season = get_object_or_404(
            Season,
            title__slug=kwargs["slug"],
            season_number=kwargs["season_number"],
        )
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        return self.render_forms(
            EpisodeForm(prefix="episode"),
            MediaVariantForm(prefix="variant"),
        )

    def post(self, request, *args, **kwargs):
        episode_form = EpisodeForm(request.POST, prefix="episode")
        variant_form = MediaVariantForm(request.POST, request.FILES, prefix="variant")

        if episode_form.is_valid() and variant_form.is_valid():
            episode = episode_form.save(commit=False)
            episode.season = self.season
            episode.save()

            variant = variant_form.save(commit=False)
            variant.episode = episode
            variant.save()
            _analyze_variant_metadata(request, variant)
            return redirect(self.season.get_absolute_url())

        return self.render_forms(episode_form, variant_form)

    def render_forms(self, episode_form, variant_form):
        from django.shortcuts import render

        return render(
            self.request,
            self.template_name,
            {
                "season": self.season,
                "episode_form": episode_form,
                "variant_form": variant_form,
                "cancel_url": self.season.get_absolute_url(),
            },
        )


class TMDBBaseMixin:
    def _tmdb_language(self, request) -> str:
        return "ru-RU" if request.LANGUAGE_CODE.startswith("ru") else "en-US"

    def _build_client(self, request) -> TMDBClient:
        legacy_value = getattr(settings, "TMDB_API_TOKEN", "")
        api_key = getattr(settings, "TMDB_API_KEY", "")
        read_access_token = getattr(settings, "TMDB_READ_ACCESS_TOKEN", "")

        if not api_key and not read_access_token and legacy_value:
            if "." in legacy_value or legacy_value.lower().startswith("bearer "):
                read_access_token = legacy_value
            else:
                api_key = legacy_value

        return TMDBClient(
            api_token=read_access_token,
            api_key=api_key,
            language=self._tmdb_language(request),
        )


class TMDBSearchView(TMDBBaseMixin, StaffJSONView):
    def get(self, request):
        query = request.GET.get("query", "").strip()
        if not query:
            return self.render_json({"results": []})

        client = self._build_client(request)
        if not client.configured():
            return self.render_json(
                {"error": "TMDB credentials are not configured."},
                status=503,
            )

        try:
            results = client.search(query)
        except TMDBError as exc:
            return self.render_json({"error": str(exc)}, status=502)

        return self.render_json({"results": results})


class TMDBSeasonSearchView(TMDBBaseMixin, StaffJSONView):
    def get(self, request):
        query = request.GET.get("query", "").strip()
        if not query:
            return self.render_json({"results": []})

        client = self._build_client(request)
        if not client.configured():
            return self.render_json(
                {"error": "TMDB credentials are not configured."},
                status=503,
            )

        try:
            results = client.search_tv(query)
        except TMDBError as exc:
            return self.render_json({"error": str(exc)}, status=502)

        return self.render_json({"results": results})


class TMDBSeasonListView(TMDBBaseMixin, StaffJSONView):
    def get(self, request):
        tmdb_id = request.GET.get("id", "").strip()
        if not tmdb_id.isdigit():
            return self.render_json({"error": "Invalid TMDB selection."}, status=400)

        client = self._build_client(request)
        if not client.configured():
            return self.render_json(
                {"error": "TMDB credentials are not configured."},
                status=503,
            )

        try:
            seasons = client.get_tv_seasons(int(tmdb_id))
        except TMDBError as exc:
            return self.render_json({"error": str(exc)}, status=502)

        return self.render_json({"seasons": seasons})


class TMDBSeasonPrefillView(TMDBBaseMixin, StaffJSONView):
    def get(self, request):
        tmdb_id = request.GET.get("id", "").strip()
        season_number = request.GET.get("season_number", "").strip()
        if not tmdb_id.isdigit() or not season_number.isdigit():
            return self.render_json({"error": "Invalid TMDB season selection."}, status=400)

        client = self._build_client(request)
        if not client.configured():
            return self.render_json(
                {"error": "TMDB credentials are not configured."},
                status=503,
            )

        try:
            data = client.get_season_prefill(int(tmdb_id), int(season_number))
        except TMDBError as exc:
            return self.render_json({"error": str(exc)}, status=502)

        return self.render_json({"result": data})


class TMDBEpisodeListView(TMDBBaseMixin, StaffJSONView):
    def get(self, request):
        tmdb_id = request.GET.get("id", "").strip()
        season_number = request.GET.get("season_number", "").strip()
        if not tmdb_id.isdigit() or not season_number.isdigit():
            return self.render_json({"error": "Invalid TMDB season selection."}, status=400)

        client = self._build_client(request)
        if not client.configured():
            return self.render_json(
                {"error": "TMDB credentials are not configured."},
                status=503,
            )

        try:
            episodes = client.get_season_episodes(int(tmdb_id), int(season_number))
        except TMDBError as exc:
            return self.render_json({"error": str(exc)}, status=502)

        return self.render_json({"episodes": episodes})


class TMDBEpisodePrefillView(TMDBBaseMixin, StaffJSONView):
    def get(self, request):
        tmdb_id = request.GET.get("id", "").strip()
        season_number = request.GET.get("season_number", "").strip()
        episode_number = request.GET.get("episode_number", "").strip()
        if (
            not tmdb_id.isdigit()
            or not season_number.isdigit()
            or not episode_number.isdigit()
        ):
            return self.render_json({"error": "Invalid TMDB episode selection."}, status=400)

        client = self._build_client(request)
        if not client.configured():
            return self.render_json(
                {"error": "TMDB credentials are not configured."},
                status=503,
            )

        try:
            data = client.get_episode_prefill(
                int(tmdb_id),
                int(season_number),
                int(episode_number),
            )
        except TMDBError as exc:
            return self.render_json({"error": str(exc)}, status=502)

        return self.render_json({"result": data})


class TMDBPrefillView(TMDBBaseMixin, StaffJSONView):
    def get(self, request):
        media_kind = request.GET.get("media_kind", "").strip()
        tmdb_id = request.GET.get("id", "").strip()

        if media_kind not in {"movie", "tv"} or not tmdb_id.isdigit():
            return self.render_json({"error": "Invalid TMDB selection."}, status=400)

        client = self._build_client(request)
        if not client.configured():
            return self.render_json(
                {"error": "TMDB credentials are not configured."},
                status=503,
            )

        try:
            data = client.get_prefill(media_kind, int(tmdb_id))
        except TMDBError as exc:
            return self.render_json({"error": str(exc)}, status=502)
        except Exception as exc:
            return self.render_json({"error": f"Prefill failed: {exc}"}, status=500)

        return self.render_json({"result": data})
