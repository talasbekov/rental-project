# booking_bot/core/storage.py — S3/MinIO storage для фото (фикс для MinIO/DEV)

import hashlib
import uuid
from io import BytesIO
import logging
import mimetypes

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import EndpointConnectionError, ClientError
from PIL import Image

from django.core.files.storage import Storage
from django.conf import settings

logger = logging.getLogger(__name__)


class S3PhotoStorage(Storage):
    """Кастомное хранилище для фотографий с оптимизацией и поддержкой MinIO"""

    def __init__(self):
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=getattr(settings, "S3_ENDPOINT_URL", None),  # напр. http://minio:9000
            aws_access_key_id=getattr(settings, "S3_ACCESS_KEY", getattr(settings, "AWS_ACCESS_KEY_ID", "")),
            aws_secret_access_key=getattr(settings, "S3_SECRET_KEY", getattr(settings, "AWS_SECRET_ACCESS_KEY", "")),
            region_name=getattr(settings, "S3_REGION", getattr(settings, "AWS_S3_REGION_NAME", "us-east-1")),
            config=BotoConfig(
                signature_version="s3v4",
                s3={"addressing_style": getattr(settings, "S3_ADDRESSING_STYLE", "path")},  # важнo для MinIO
            ),
            use_ssl=getattr(settings, "S3_USE_SSL", False),
            verify=getattr(settings, "S3_USE_SSL", False),
        )
        self.bucket_name = getattr(settings, "S3_BUCKET_NAME", getattr(settings, "AWS_STORAGE_BUCKET_NAME", "jgo-photos"))
        self.public_base = getattr(settings, "S3_PUBLIC_BASE", "").rstrip("/")  # напр. http://localhost:9000/jgo-photos

        self.max_size = getattr(settings, "PHOTO_MAX_SIZE", 5 * 1024 * 1024)   # 5MB
        self.max_dimension = getattr(settings, "PHOTO_MAX_DIMENSION", 1920)
        self.thumbnail_size = getattr(settings, "PHOTO_THUMBNAIL_SIZE", (400, 300))

    # ---------- image utils ----------

    def _validate_image(self, file_obj):
        """Валидация изображения"""
        size = getattr(file_obj, "size", None)
        if size is not None and size > self.max_size:
            raise ValueError(f"Файл слишком большой. Максимум {self.max_size / 1024 / 1024:.1f} МБ")

        try:
            img = Image.open(file_obj)
            if img.format not in ("JPEG", "PNG", "WEBP"):
                raise ValueError(f"Неподдерживаемый формат: {img.format}")
        except Exception as e:
            raise ValueError(f"Невалидное изображение: {e}")
        return img

    def _optimize_image(self, img, quality=85):
        """Оптимизация изображения. Возвращает (bytes_io, ext_without_dot, width, height)"""
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")

        # даунскейл, если нужно
        if img.width > self.max_dimension or img.height > self.max_dimension:
            img.thumbnail((self.max_dimension, self.max_dimension), Image.Resampling.LANCZOS)

        # формат: если RGBA оставим WEBP, иначе JPEG
        use_webp = (img.mode == "RGBA")
        out = BytesIO()
        if use_webp:
            img.save(out, format="WEBP", quality=quality, method=6)
            ext = "webp"
            ctype = "image/webp"
        else:
            img.save(out, format="JPEG", quality=quality, optimize=True)
            ext = "jpg"
            ctype = "image/jpeg"
        out.seek(0)
        return out, ext, img.width, img.height, ctype

    def _create_thumbnail(self, img):
        """Создание миниатюры (JPEG)"""
        thumb = img.copy()
        # ИСПРАВЛЕНИЕ: конвертируем RGBA -> RGB перед сохранением в JPEG (Claude Code)
        if thumb.mode == "RGBA":
            # Создаём белый фон для прозрачных областей
            background = Image.new("RGB", thumb.size, (255, 255, 255))
            background.paste(thumb, mask=thumb.split()[3])  # alpha channel as mask
            thumb = background
        elif thumb.mode not in ("RGB", "L"):
            thumb = thumb.convert("RGB")

        thumb.thumbnail(self.thumbnail_size, Image.Resampling.LANCZOS)
        out = BytesIO()
        thumb.save(out, format="JPEG", quality=80, optimize=True)
        out.seek(0)
        return out

    def _generate_basename(self, optimized_bytes: bytes):
        """Имя файла: properties/<md5_8>_<uuid8>.<ext> (без расширения; ext добавим отдельно)"""
        h = hashlib.md5(optimized_bytes).hexdigest()[:8]
        uid = uuid.uuid4().hex[:8]
        return f"properties/{h}_{uid}"

    # ---------- Storage API ----------

    def _save(self, name, content):
        """Сохранение файла в S3/MinIO"""
        try:
            # 1) валидация + оптимизация
            content.seek(0)
            img = self._validate_image(content)
            optimized_io, ext, width, height, content_type = self._optimize_image(img)

            # 2) имена ключей
            base = self._generate_basename(optimized_io.getbuffer())
            key_main = f"{base}.{ext}"
            key_thumb = f"{base}_thumb.jpg"

            # 3) заливаем основное изображение
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key_main,
                Body=optimized_io.getvalue(),
                ContentType=content_type,
                CacheControl="max-age=31536000",  # 1 год
                Metadata={
                    "original_name": name,
                    "width": str(width),
                    "height": str(height),
                },
                ACL="public-read",  # в DEV удобно; в PROD можно убрать и открыть бакет политикой
            )

            # 4) превью
            thumb_io = self._create_thumbnail(img)
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key_thumb,
                Body=thumb_io.getvalue(),
                ContentType="image/jpeg",
                CacheControl="max-age=31536000",
                ACL="public-read",
            )

            logger.info("Uploaded photo: %s and thumbnail: %s", key_main, key_thumb)
            return key_main

        except (EndpointConnectionError, ClientError) as e:
            logger.error("S3 client error: %s", e)
            raise
        except Exception as e:
            logger.error("Error uploading photo: %s", e)
            raise

    def delete(self, name):
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=name)
            thumb = name.rsplit(".", 1)[0] + "_thumb.jpg"
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=thumb)
            logger.info("Deleted photo: %s (+thumb)", name)
        except Exception as e:
            logger.error("Error deleting photo: %s", e)

    def exists(self, name):
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=name)
            return True
        except Exception:
            return False

    def _public_url_from_base(self, key: str) -> str:
        base = (self.public_base or "").rstrip("/")
        if base:
            return f"{base}/{key.lstrip('/')}"
        return ""

    def url(self, name):
        """Публичный URL к объекту
        приоритет:
        1) S3_PUBLIC_BASE (напр. http://localhost:9000/jgo-photos/key)
        2) AWS_CLOUDFRONT_DOMAIN (https://cdn.example.com/key)
        3) endpoint + path-style (http://minio:9000/bucket/key) — НЕ для внешнего мира
        4) presigned URL (на крайний случай)
        """
        # 1) явная публичная база (рекомендуется в DEV/MinIO за пределами Docker)
        url = self._public_url_from_base(name)
        if url:
            return url

        # 2) CDN
        cdn = getattr(settings, "AWS_CLOUDFRONT_DOMAIN", None)
        if cdn:
            return f"https://{cdn}/{name.lstrip('/')}"

        # 3) endpoint + path-style (подойдёт для внутренней сети; снаружи может быть недоступно)
        endpoint = getattr(settings, "S3_ENDPOINT_URL", "").rstrip("/")
        if endpoint:
            return f"{endpoint}/{self.bucket_name}/{name.lstrip('/')}"

        # 4) подпись на 1 час — если бакет приватный/ничего выше нет
        try:
            return self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": name},
                ExpiresIn=3600,
            )
        except Exception as e:
            logger.error("Cannot build URL for %s: %s", name, e)
            # худший случай — вернём ключ
            return f"/media/{name}"

    def get_thumbnail_url(self, name):
        thumb_name = name.rsplit(".", 1)[0] + "_thumb.jpg"
        return self.url(thumb_name)
