"""Location models with MPPT tree structure for cities and districts."""

from django.db import models
from mptt.models import MPTTModel, TreeForeignKey


class Location(MPTTModel):
    """Hierarchical location model for cities and districts using MPTT."""

    name = models.CharField(
        max_length=255,
        verbose_name="Название",
        help_text="Название города или района"
    )
    parent = TreeForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name="Родительская локация",
        help_text="Для района - это город, для города - пусто"
    )
    slug = models.SlugField(
        max_length=255,
        unique=True,
        verbose_name="Слаг",
        help_text="URL-friendly название"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна",
        help_text="Отображать в списке выбора"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class MPTTMeta:
        order_insertion_by = ['name']

    class Meta:
        verbose_name = "Локация"
        verbose_name_plural = "Локации"
        ordering = ['tree_id', 'lft']
        indexes = [
            models.Index(fields=['parent', 'name']),
            models.Index(fields=['slug']),
        ]

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} - {self.name}"
        return self.name

    @property
    def is_city(self):
        """Проверяет, является ли локация городом (без родителя)."""
        return self.parent is None

    @property
    def is_district(self):
        """Проверяет, является ли локация районом (есть родитель-город)."""
        return self.parent is not None

    def get_full_path(self):
        """Возвращает полный путь локации через родителей."""
        if self.parent:
            return f"{self.parent.name}, {self.name}"
        return self.name
