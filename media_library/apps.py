from django.apps import AppConfig


class MediaLibraryConfig(AppConfig):
    name = "media_library"

    def ready(self):
        import media_library.signals  # noqa: F401
