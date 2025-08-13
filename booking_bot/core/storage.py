# booking_bot/core/storage.py - Система хранения фотографий

import boto3
from PIL import Image
from io import BytesIO
import hashlib
import uuid

from django.core.files.storage import Storage
from django.core.files.base import ContentFile
import logging

from booking_bot import settings

logger = logging.getLogger(__name__)


class S3PhotoStorage(Storage):
    """Кастомное хранилище для фотографий с оптимизацией"""

    def __init__(self):
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=getattr(settings, "S3_ENDPOINT_URL", None),
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=getattr(settings, "AWS_S3_REGION_NAME", "us-east-1"),
        )
        self.bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        self.max_size = getattr(settings, "PHOTO_MAX_SIZE", 5 * 1024 * 1024)  # 5MB
        self.max_dimension = getattr(settings, "PHOTO_MAX_DIMENSION", 1920)
        self.thumbnail_size = getattr(settings, "PHOTO_THUMBNAIL_SIZE", (400, 300))

    def _validate_image(self, file):
        """Валидация изображения"""
        # Проверка размера файла
        if file.size > self.max_size:
            raise ValueError(
                f"Файл слишком большой. Максимум {self.max_size / 1024 / 1024:.1f} МБ"
            )

        # Проверка формата
        try:
            img = Image.open(file)
            if img.format not in ["JPEG", "PNG", "WEBP"]:
                raise ValueError(f"Неподдерживаемый формат: {img.format}")
        except Exception as e:
            raise ValueError(f"Невалидное изображение: {e}")

        return img

    def _optimize_image(self, img, quality=85):
        """Оптимизация изображения"""
        # Конвертируем в RGB если нужно
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")

        # Изменяем размер если слишком большое
        if img.width > self.max_dimension or img.height > self.max_dimension:
            img.thumbnail(
                (self.max_dimension, self.max_dimension), Image.Resampling.LANCZOS
            )

        # Сохраняем в буфер
        output = BytesIO()
        img_format = "WEBP" if img.mode == "RGBA" else "JPEG"
        img.save(output, format=img_format, quality=quality, optimize=True)
        output.seek(0)

        return output, img_format.lower()

    def _create_thumbnail(self, img):
        """Создание миниатюры"""
        thumb = img.copy()
        thumb.thumbnail(self.thumbnail_size, Image.Resampling.LANCZOS)

        output = BytesIO()
        thumb.save(output, format="JPEG", quality=80, optimize=True)
        output.seek(0)

        return output

    def _generate_filename(self, name, content):
        """Генерация уникального имени файла"""
        # Хэш контента для дедупликации
        hasher = hashlib.md5()
        for chunk in content.chunks():
            hasher.update(chunk)
        content_hash = hasher.hexdigest()[:8]

        # Генерируем имя
        ext = name.split(".")[-1].lower()
        unique_id = uuid.uuid4().hex[:8]

        return f"properties/{content_hash}_{unique_id}.{ext}"

    def _save(self, name, content):
        """Сохранение файла в S3"""
        try:
            # Валидация
            content.seek(0)
            img = self._validate_image(content)

            # Оптимизация основного изображения
            optimized, img_format = self._optimize_image(img)

            # Генерируем имена файлов
            base_name = self._generate_filename(name, content)
            thumb_name = base_name.replace(f".{img_format}", f"_thumb.jpg")

            # Загружаем основное изображение
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=base_name,
                Body=optimized.getvalue(),
                ContentType=f"image/{img_format}",
                CacheControl="max-age=31536000",  # 1 год
                Metadata={
                    "original_name": name,
                    "width": str(img.width),
                    "height": str(img.height),
                },
            )

            # Создаем и загружаем миниатюру
            thumbnail = self._create_thumbnail(img)
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=thumb_name,
                Body=thumbnail.getvalue(),
                ContentType="image/jpeg",
                CacheControl="max-age=31536000",
            )

            logger.info(f"Uploaded photo: {base_name} and thumbnail: {thumb_name}")

            return base_name

        except Exception as e:
            logger.error(f"Error uploading photo: {e}")
            raise

    def delete(self, name):
        """Удаление файла из S3"""
        try:
            # Удаляем основное изображение
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=name)

            # Удаляем миниатюру
            thumb_name = name.rsplit(".", 1)[0] + "_thumb.jpg"
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=thumb_name)

            logger.info(f"Deleted photo: {name}")
        except Exception as e:
            logger.error(f"Error deleting photo: {e}")

    def exists(self, name):
        """Проверка существования файла"""
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=name)
            return True
        except:
            return False

    def url(self, name):
        """Получение URL для доступа к файлу"""
        # Если используем CloudFront
        if hasattr(settings, "AWS_CLOUDFRONT_DOMAIN"):
            return f"https://{settings.AWS_CLOUDFRONT_DOMAIN}/{name}"

        # Прямая ссылка на S3
        return f"https://{self.bucket_name}.s3.amazonaws.com/{name}"

    def get_thumbnail_url(self, name):
        """Получение URL миниатюры"""
        thumb_name = name.rsplit(".", 1)[0] + "_thumb.jpg"
        return self.url(thumb_name)
