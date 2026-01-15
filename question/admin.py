from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Chapter,
    ClassName,
    Concept,
    CroppedImage,
    CroppedImageExtra,
    ImageType,
    QuestionType,
    QuestionUsage,
    Sources,
    Subject,
    Topic,
    UsageType,
)


class BaseNamedAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "created_at", "updated_at")
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")
    ordering = ("name",)


@admin.register(ClassName)
class ClassNameAdmin(BaseNamedAdmin):
    pass


@admin.register(Subject)
class SubjectAdmin(BaseNamedAdmin):
    pass


@admin.register(ImageType)
class ImageTypeAdmin(BaseNamedAdmin):
    pass


@admin.register(QuestionType)
class QuestionTypeAdmin(BaseNamedAdmin):
    pass


@admin.register(UsageType)
class UsageTypeAdmin(BaseNamedAdmin):
    pass


@admin.register(Sources)
class SourcesAdmin(BaseNamedAdmin):
    pass


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "class_name", "subject", "created_at", "updated_at")
    search_fields = ("name", "class_name__name", "subject__name")
    list_filter = ("class_name", "subject")
    autocomplete_fields = ("class_name", "subject")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Concept)
class ConceptAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "chapter", "created_at", "updated_at")
    search_fields = ("name", "chapter__name")
    list_filter = ("chapter",)
    autocomplete_fields = ("chapter",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "concept", "created_at", "updated_at")
    search_fields = ("name", "concept__name")
    list_filter = ("concept",)
    autocomplete_fields = ("concept",)
    readonly_fields = ("created_at", "updated_at")


class QuestionUsageInline(admin.TabularInline):
    model = QuestionUsage
    extra = 0
    autocomplete_fields = ("usage_type",)


class CroppedImageExtraInline(admin.TabularInline):
    model = CroppedImageExtra
    extra = 0
    fields = ("sort_order", "image_preview", "image", "image_type", "created_at")
    readonly_fields = ("image_preview", "created_at")
    autocomplete_fields = ("image_type",)
    ordering = ("sort_order", "id")

    def image_preview(self, obj):
        if not obj or not getattr(obj, "image", None):
            return ""
        try:
            url = obj.image.url
        except Exception:
            return ""
        return format_html(
            '<a href="{0}" target="_blank"><img src="{0}" style="height:60px; border:1px solid #ddd;" /></a>',
            url,
        )

    image_preview.short_description = "Preview"


@admin.register(CroppedImageExtra)
class CroppedImageExtraAdmin(admin.ModelAdmin):
    list_display = ("id", "parent", "image_type", "created_at")
    search_fields = ("id", "parent__id")
    list_filter = ("image_type",)
    autocomplete_fields = ("parent", "image_type")
    readonly_fields = ("created_at", "updated_at")

@admin.register(CroppedImage)
class CroppedImageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "class_name",
        "subject",
        "chapter",
        "concept",
        "topic",
        "question_type",
        "difficulty",
        "marks",
        "priority",
        "verified",
        "is_active",
        "created_at",
    )
    readonly_fields = ("created_at", "updated_at")
    search_fields = (
        "id",
        "class_name__name",
        "subject__name",
        "chapter__name",
        "concept__name",
        "topic__name",
        "question_type__name",
    )
    list_filter = ("difficulty", "verified", "is_active", "priority", "question_type")
    list_select_related = (
        "class_name",
        "subject",
        "chapter",
        "concept",
        "topic",
        "question_type",
        "image_type",
        "source",
    )
    autocomplete_fields = (
        "class_name",
        "subject",
        "chapter",
        "concept",
        "topic",
        "question_type",
        "image_type",
        "source",
    )
    readonly_fields = ("created_at", "updated_at")
    inlines = (QuestionUsageInline, CroppedImageExtraInline)
