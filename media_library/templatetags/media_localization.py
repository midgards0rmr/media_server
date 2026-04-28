from django import template
from django.utils.translation import get_language

register = template.Library()


def _language_code(language_code: str | None = None) -> str:
    return (language_code or get_language() or "").split("-")[0]


@register.filter
def localized_title(media_title, language_code: str | None = None) -> str:
    if not media_title:
        return ""

    language = _language_code(language_code)
    if hasattr(media_title, "get_localized_title"):
        return media_title.get_localized_title(language)

    return str(media_title)


@register.filter
def localized_description(media_title, language_code: str | None = None) -> str:
    if not media_title:
        return ""

    language = _language_code(language_code)
    if hasattr(media_title, "get_localized_description"):
        return media_title.get_localized_description(language)

    return getattr(media_title, "description", "") or ""
