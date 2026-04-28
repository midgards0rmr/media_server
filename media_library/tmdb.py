from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.core.files import File

from media_library.models import MediaImage, MediaTitle

TMDB_API_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"


class TMDBError(Exception):
    pass


class TMDBClient:
    def __init__(
        self,
        api_token: str = "",
        api_key: str = "",
        language: str = "ru-RU",
    ):
        self.api_token = self._normalize_token(api_token)
        self.api_key = api_key.strip()
        self.language = language

    def configured(self) -> bool:
        return bool(self.api_token or self.api_key)

    def _request(self, path: str, params: dict[str, str] | None = None) -> dict:
        if not self.configured():
            raise TMDBError("TMDB credentials are not configured.")

        credentials = self._credential_candidates()
        last_auth_error = None

        for credential_type, credential_value in credentials:
            query_params = dict(params or {})
            headers = {"accept": "application/json"}

            if credential_type == "api_key":
                query_params["api_key"] = credential_value
            else:
                headers["Authorization"] = f"Bearer {credential_value}"

            query = urlencode(query_params)
            url = f"{TMDB_API_BASE}{path}"
            if query:
                url = f"{url}?{query}"

            request = Request(url, headers=headers)

            try:
                with urlopen(request, timeout=10) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="ignore")
                if exc.code in {401, 403}:
                    last_auth_error = exc
                    continue
                raise TMDBError(
                    f"TMDB request failed with HTTP {exc.code}. {detail}".strip()
                ) from exc
            except URLError as exc:
                reason = getattr(exc, "reason", exc)
                raise TMDBError(f"TMDB request failed: {reason}") from exc
            except TimeoutError as exc:
                raise TMDBError("TMDB request timed out.") from exc

        if last_auth_error is not None:
            raise TMDBError(
                "TMDB rejected credentials. Check whether you set API Key or Read Access Token correctly."
            ) from last_auth_error

        raise TMDBError("TMDB credentials are not configured.")

    def _normalize_token(self, token: str) -> str:
        value = token.strip()
        if value.lower().startswith("bearer "):
            value = value[7:].strip()
        return value

    def _credential_candidates(self) -> list[tuple[str, str]]:
        candidates: list[tuple[str, str]] = []

        if self.api_token:
            candidates.append(("api_token", self.api_token))
        if self.api_key:
            candidates.append(("api_key", self.api_key))

        normalized_candidates: list[tuple[str, str]] = []
        seen = set()
        for credential_type, credential_value in candidates:
            actual_type = credential_type
            if credential_type == "api_key" and "." in credential_value:
                actual_type = "api_token"
            elif credential_type == "api_token" and "." not in credential_value:
                actual_type = "api_key"

            key = (actual_type, credential_value)
            if key not in seen:
                seen.add(key)
                normalized_candidates.append(key)

        return normalized_candidates

    def search(self, query: str, limit: int = 8) -> list[dict]:
        movie_results = self._request(
            "/search/movie",
            {"query": query, "language": self.language, "page": "1"},
        ).get("results", [])
        tv_results = self._request(
            "/search/tv",
            {"query": query, "language": self.language, "page": "1"},
        ).get("results", [])

        combined = [
            self._serialize_search_item("movie", item) for item in movie_results[:limit]
        ] + [
            self._serialize_search_item("tv", item) for item in tv_results[:limit]
        ]
        combined.sort(
            key=lambda item: (
                item.get("popularity", 0),
                item.get("release_date") or "",
            ),
            reverse=True,
        )
        return combined[:limit]

    def search_tv(self, query: str, limit: int = 8) -> list[dict]:
        tv_results = self._request(
            "/search/tv",
            {"query": query, "language": self.language, "page": "1"},
        ).get("results", [])
        combined = [self._serialize_search_item("tv", item) for item in tv_results]
        combined.sort(
            key=lambda item: (
                item.get("popularity", 0),
                item.get("release_date") or "",
            ),
            reverse=True,
        )
        return combined[:limit]

    def get_prefill(self, media_kind: str, tmdb_id: int) -> dict:
        endpoint = "/movie/" if media_kind == "movie" else "/tv/"
        item = self._request(
            f"{endpoint}{tmdb_id}",
            {"language": self.language},
        )
        localized_items = self._localized_detail_items(media_kind, tmdb_id)
        return self._serialize_detail_item(media_kind, item, localized_items)

    def get_tv_seasons(self, tmdb_id: int) -> list[dict]:
        item = self._request(f"/tv/{tmdb_id}", {"language": self.language})
        seasons = item.get("seasons") or []
        return [
            self._serialize_season_search_item(season)
            for season in seasons
            if isinstance(season.get("season_number"), int) and season.get("season_number") > 0
        ]

    def get_season_prefill(self, tmdb_id: int, season_number: int) -> dict:
        item = self._request(
            f"/tv/{tmdb_id}/season/{season_number}",
            {"language": self.language},
        )
        return self._serialize_season_detail_item(item)

    def get_season_episodes(self, tmdb_id: int, season_number: int) -> list[dict]:
        item = self._request(
            f"/tv/{tmdb_id}/season/{season_number}",
            {"language": self.language},
        )
        episodes = item.get("episodes") or []
        return [self._serialize_episode_search_item(episode) for episode in episodes]

    def get_episode_prefill(
        self,
        tmdb_id: int,
        season_number: int,
        episode_number: int,
    ) -> dict:
        item = self._request(
            f"/tv/{tmdb_id}/season/{season_number}/episode/{episode_number}",
            {"language": self.language},
        )
        return self._serialize_episode_detail_item(item)

    def _serialize_search_item(self, media_kind: str, item: dict) -> dict:
        title = item.get("title") or item.get("name") or ""
        original_title = item.get("original_title") or item.get("original_name") or ""
        release_date = item.get("release_date") or item.get("first_air_date") or ""
        return {
            "id": item.get("id"),
            "media_kind": media_kind,
            "title": title,
            "original_title": original_title,
            "overview": item.get("overview") or "",
            "release_date": release_date,
            "poster_url": self._image_url(item.get("poster_path"), "w342"),
            "backdrop_url": self._image_url(item.get("backdrop_path"), "w780"),
            "popularity": item.get("popularity", 0),
        }

    def _serialize_season_search_item(self, item: dict) -> dict:
        air_date = item.get("air_date") or ""
        return {
            "season_number": item.get("season_number"),
            "name": item.get("name") or "",
            "overview": item.get("overview") or "",
            "air_date": air_date,
            "episode_count": item.get("episode_count") or 0,
            "poster_url": self._image_url(item.get("poster_path"), "w342"),
        }

    def _serialize_season_detail_item(self, item: dict) -> dict:
        air_date = item.get("air_date") or ""
        return {
            "season_number": item.get("season_number"),
            "name": item.get("name") or "",
            "description": item.get("overview") or "",
            "release_year": int(air_date[:4]) if air_date else None,
            "air_date": air_date,
            "episode_count": len(item.get("episodes") or []),
        }

    def _serialize_episode_search_item(self, item: dict) -> dict:
        air_date = item.get("air_date") or ""
        return {
            "episode_number": item.get("episode_number"),
            "title": item.get("name") or "",
            "description": item.get("overview") or "",
            "air_date": air_date,
            "runtime": item.get("runtime"),
            "still_url": self._image_url(item.get("still_path"), "w300"),
        }

    def _serialize_episode_detail_item(self, item: dict) -> dict:
        air_date = item.get("air_date") or ""
        return {
            "episode_number": item.get("episode_number"),
            "title": item.get("name") or "",
            "description": item.get("overview") or "",
            "release_date": air_date,
            "duration_minutes": item.get("runtime"),
            "still_url": self._image_url(item.get("still_path"), "w300"),
        }

    def _localized_detail_items(self, media_kind: str, tmdb_id: int) -> dict[str, dict]:
        endpoint = "/movie/" if media_kind == "movie" else "/tv/"
        languages = [self.language, "ru-RU", "en-US"]
        items = {}

        for language in dict.fromkeys(languages):
            try:
                items[language.split("-")[0]] = self._request(
                    f"{endpoint}{tmdb_id}",
                    {"language": language},
                )
            except TMDBError:
                continue

        return items

    def _serialize_detail_item(
        self,
        media_kind: str,
        item: dict,
        localized_items: dict[str, dict] | None = None,
    ) -> dict:
        original_language = item.get("original_language") or ""
        genres = [genre["name"] for genre in item.get("genres", []) if genre.get("name")]
        countries = []
        if media_kind == "movie":
            countries = [
                country["name"]
                for country in item.get("production_countries", [])
                if country.get("name")
            ]
        else:
            countries = [
                country
                for country in item.get("origin_country", [])
                if isinstance(country, str) and country
            ]

        title = item.get("title") or item.get("name") or ""
        original_title = item.get("original_title") or item.get("original_name") or ""
        release_date = item.get("release_date") or item.get("first_air_date") or ""

        title_localizations = self._title_localizations(
            title,
            original_title,
            localized_items or {},
        )
        description_localizations = self._description_localizations(
            item.get("overview") or "",
            localized_items or {},
        )

        return {
            "title": title,
            "title_localizations": title_localizations,
            "original_title": original_title,
            "description": item.get("overview") or "",
            "description_localizations": description_localizations,
            "media_type": self._guess_media_type(media_kind, genres, original_language),
            "status": self._guess_status(item.get("status"), media_kind),
            "release_year": int(release_date[:4]) if release_date else None,
            "genres": genres,
            "countries": countries,
            "language": original_language,
            "poster_url": self._image_url(item.get("poster_path"), "w780"),
            "backdrop_url": self._image_url(item.get("backdrop_path"), "w780"),
        }

    def _guess_media_type(
        self, media_kind: str, genres: list[str], original_language: str
    ) -> str:
        lower_genres = {genre.lower() for genre in genres}
        if media_kind == "movie":
            return MediaTitle.MediaType.CARTOON if "animation" in lower_genres else MediaTitle.MediaType.MOVIE
        if "animation" in lower_genres and original_language == "ja":
            return MediaTitle.MediaType.ANIME
        if "animation" in lower_genres:
            return MediaTitle.MediaType.CARTOON
        return MediaTitle.MediaType.SERIES

    def _guess_status(self, tmdb_status: str | None, media_kind: str) -> str:
        if not tmdb_status:
            return MediaTitle.Status.RELEASED
        status = tmdb_status.lower()
        if status in {"planned", "in production"}:
            return MediaTitle.Status.ANNOUNCED
        if status in {"returning series", "pilot", "post production"}:
            return MediaTitle.Status.ONGOING
        if status in {"ended", "released", "canceled"}:
            return MediaTitle.Status.RELEASED
        return MediaTitle.Status.RELEASED

    def _title_localizations(
        self,
        title: str,
        original_title: str,
        localized_items: dict[str, dict],
    ) -> dict[str, str]:
        values = {}
        for language, item in localized_items.items():
            localized_title = item.get("title") or item.get("name") or ""
            if localized_title:
                values[language] = localized_title

        current_language = self.language.split("-")[0]
        if title:
            values.setdefault(current_language, title)
        if original_title:
            values.setdefault("en", original_title)
        return values

    def _description_localizations(
        self,
        description: str,
        localized_items: dict[str, dict],
    ) -> dict[str, str]:
        values = {}
        for language, item in localized_items.items():
            overview = item.get("overview") or ""
            if overview:
                values[language] = overview

        current_language = self.language.split("-")[0]
        if description:
            values.setdefault(current_language, description)
        return values

    def _image_url(self, path: str | None, size: str) -> str:
        if not path:
            return ""
        return f"{TMDB_IMAGE_BASE}/{size}{path}"


def download_tmdb_image(media_title: MediaTitle, image_url: str, image_type: str) -> MediaImage | None:
    if not image_url:
        return None

    request = Request(image_url, headers={"accept": "image/*"})
    try:
        with urlopen(request, timeout=15) as response:
            suffix = Path(image_url).suffix or ".jpg"
            with NamedTemporaryFile(suffix=suffix) as temp_file:
                temp_file.write(response.read())
                temp_file.flush()
                image = MediaImage(
                    media_title=media_title,
                    image_type=image_type,
                    title=media_title.title,
                    is_primary=image_type == MediaImage.ImageType.POSTER,
                )
                image.image.save(
                    f"{image_type}{suffix}",
                    File(open(temp_file.name, "rb")),
                    save=False,
                )
                image.save()
                return image
    except (HTTPError, URLError, TimeoutError, OSError):
        return None
