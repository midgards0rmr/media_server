from django.urls import path

from media_library.views import (
    EpisodeCreateView,
    EpisodeVariantCreateView,
    EpisodeWithVariantCreateView,
    MediaFileCreateView,
    MediaFileDeleteView,
    MediaFileDetailView,
    MediaFileListView,
    MediaFileUpdateView,
    HLSMediaView,
    MediaProcessingJobStatusView,
    MediaVariantStreamView,
    SeasonDetailView,
    SeasonCreateView,
    TMDBEpisodeListView,
    TMDBEpisodePrefillView,
    TMDBPrefillView,
    TMDBSeasonListView,
    TMDBSeasonPrefillView,
    TMDBSeasonSearchView,
    TMDBSearchView,
    TitleVariantCreateView,
)

app_name = "media_library"

urlpatterns = [
    path("", MediaFileListView.as_view(), name="mediafile_list"),
    path("media/add/", MediaFileCreateView.as_view(), name="mediafile_create"),
    path("media/import/search/", TMDBSearchView.as_view(), name="tmdb_search"),
    path("media/import/prefill/", TMDBPrefillView.as_view(), name="tmdb_prefill"),
    path(
        "media/import/seasons/search/",
        TMDBSeasonSearchView.as_view(),
        name="tmdb_season_search",
    ),
    path(
        "media/import/seasons/list/",
        TMDBSeasonListView.as_view(),
        name="tmdb_season_list",
    ),
    path(
        "media/import/seasons/prefill/",
        TMDBSeasonPrefillView.as_view(),
        name="tmdb_season_prefill",
    ),
    path(
        "media/import/episodes/list/",
        TMDBEpisodeListView.as_view(),
        name="tmdb_episode_list",
    ),
    path(
        "media/import/episodes/prefill/",
        TMDBEpisodePrefillView.as_view(),
        name="tmdb_episode_prefill",
    ),
    path(
        "media/library/<path:path>",
        HLSMediaView.as_view(),
        {"root": "library"},
        name="library_media",
    ),
    path("media/hls/<path:path>", HLSMediaView.as_view(), name="hls_media"),
    path(
        "media/variants/<int:pk>/stream/",
        MediaVariantStreamView.as_view(),
        name="media_variant_stream",
    ),
    path(
        "media/processing-jobs/<int:pk>/status/",
        MediaProcessingJobStatusView.as_view(),
        name="media_processing_job_status",
    ),
    path(
        "media/<slug:slug>/variants/add/",
        TitleVariantCreateView.as_view(),
        name="title_variant_create",
    ),
    path(
        "media/<slug:slug>/seasons/add/",
        SeasonCreateView.as_view(),
        name="season_create",
    ),
    path(
        "media/<slug:slug>/season/<int:season_number>/",
        SeasonDetailView.as_view(),
        name="season_detail",
    ),
    path(
        "media/<slug:slug>/season/<int:season_number>/episodes/add/",
        EpisodeCreateView.as_view(),
        name="episode_create",
    ),
    path(
        "media/<slug:slug>/season/<int:season_number>/episodes/add-with-file/",
        EpisodeWithVariantCreateView.as_view(),
        name="episode_with_variant_create",
    ),
    path(
        "media/<slug:slug>/season/<int:season_number>/episode/<int:episode_number>/variants/add/",
        EpisodeVariantCreateView.as_view(),
        name="episode_variant_create",
    ),
    path(
        "media/<slug:slug>/edit/",
        MediaFileUpdateView.as_view(),
        name="mediafile_update",
    ),
    path(
        "media/<slug:slug>/delete/",
        MediaFileDeleteView.as_view(),
        name="mediafile_delete",
    ),
    path("media/<slug:slug>/", MediaFileDetailView.as_view(), name="mediafile_detail"),
]
