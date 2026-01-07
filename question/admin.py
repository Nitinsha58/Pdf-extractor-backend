from django.contrib import admin
from .models import (
    Chapter,
    ClassName,
    Concept,
    CroppedImage,
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
    inlines = (QuestionUsageInline,)
