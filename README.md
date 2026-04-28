# Media Server

Django-приложение для ведения домашней медиатеки с фильмами и сериалами.

Проект умеет:
- хранить карточки фильмов, сериалов, сезонов и эпизодов;
- загружать видеофайлы и привязывать их к тайтлам или эпизодам;
- анализировать медиа через `ffprobe` и извлекать метаданные дорожек;
- извлекать текстовые субтитры в `WebVTT`;
- генерировать HLS-потоки (`.m3u8` + `.ts`) для браузерного воспроизведения;
- показывать постеры и дополнительные изображения;
- импортировать часть данных о тайтлах, сезонах и эпизодах из TMDB;
- использовать обычную сессионную авторизацию и JWT API для аккаунта.

## Стек

- Python 3.14
- Django 6
- Poetry
- PostgreSQL
- FFmpeg / ffprobe
- Pillow
- Django REST Framework
- SimpleJWT

## Требования

Перед запуском должны быть установлены:
- `python` 3.14
- `poetry`
- `postgresql`
- `ffmpeg`
- `ffprobe`

## Установка

```bash
poetry install
```

## Настройка окружения

Проект читает переменные окружения из файла `config/.env`.

Минимальный пример:

```env
DB_NAME=media_server
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=127.0.0.1
DB_PORT=5432
```

Дополнительные полезные переменные:

```env
MEDIA_UPLOAD_MAX_SIZE=21474836480
HLS_SEGMENT_TIME=12
DELETE_ORIGINAL_AFTER_HLS=True

TMDB_API_TOKEN=
TMDB_API_KEY=
TMDB_READ_ACCESS_TOKEN=
```

Примечания:
- без корректного `config/.env` Django не сможет подключиться к базе;
- интеграция с TMDB необязательна, но без токена поиск и предзаполнение не будут работать;
- `DELETE_ORIGINAL_AFTER_HLS=True` удаляет исходный загруженный файл после успешной генерации HLS.

## Первичный запуск

```bash
poetry run python manage.py migrate
poetry run python manage.py createsuperuser
poetry run python manage.py runserver
```