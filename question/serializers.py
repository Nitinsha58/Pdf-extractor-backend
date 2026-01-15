from rest_framework import serializers
from .models import (
    Chapter,
    ClassName,
    Concept,
    CroppedImage,
    CroppedImageExtra,
    ImageType,
    QuestionType,
    Sources,
    Subject,
    Topic,
    UsageType,
)


class ClassNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassName
        fields = ("id", "name")


class ClassNameWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassName
        fields = ("id", "name")


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ("id", "name")


class SubjectWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ("id", "name")


class ChapterSerializer(serializers.ModelSerializer):
    class_name = ClassNameSerializer(read_only=True)
    subject = SubjectSerializer(read_only=True)

    class_name_id = serializers.IntegerField(read_only=True)
    subject_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Chapter
        fields = ("id", "name", "class_name", "subject", "class_name_id", "subject_id")


class ChapterWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chapter
        fields = ("id", "name", "class_name", "subject")


class ConceptSerializer(serializers.ModelSerializer):
    chapter = ChapterSerializer(read_only=True)
    chapter_id = serializers.IntegerField(read_only=True)
    class_name_id = serializers.IntegerField(source="chapter.class_name_id", read_only=True)
    subject_id = serializers.IntegerField(source="chapter.subject_id", read_only=True)

    class Meta:
        model = Concept
        fields = (
            "id",
            "name",
            "chapter",
            "chapter_id",
            "class_name_id",
            "subject_id",
        )


class ConceptWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Concept
        fields = ("id", "name", "chapter")


class TopicSerializer(serializers.ModelSerializer):
    concept_id = serializers.IntegerField(read_only=True)
    class_name_id = serializers.IntegerField(source="concept.chapter.class_name_id", read_only=True)
    subject_id = serializers.IntegerField(source="concept.chapter.subject_id", read_only=True)
    chapter_id = serializers.IntegerField(source="concept.chapter_id", read_only=True)

    class Meta:
        model = Topic
        fields = (
            "id",
            "name",
            "concept_id",
            "class_name_id",
            "subject_id",
            "chapter_id",
        )


class TopicWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Topic
        fields = ("id", "name", "concept")


class ImageTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImageType
        fields = ("id", "name")


class QuestionTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionType
        fields = ("id", "name")


class UsageTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = UsageType
        fields = ("id", "name")


class SourcesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sources
        fields = ("id", "name")


class CropSerializer(serializers.ModelSerializer):
    # NOTE: Upload endpoints still use this serializer.
    class Meta:
        model = CroppedImage
        fields = "__all__"


class CroppedImageWriteSerializer(serializers.ModelSerializer):
    usage_types = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=UsageType.objects.all(),
        required=False,
    )

    class Meta:
        model = CroppedImage
        fields = (
            "id",
            "image_type",
            "rect_pdf",
            "rect_screen",
            "class_name",
            "subject",
            "chapter",
            "concept",
            "topic",
            "question_type",
            "difficulty",
            "marks",
            "usage_types",
            "priority",
            "verified",
            "source",
            "is_active",
        )
        read_only_fields = ("id",)


class CroppedImageExtraReadSerializer(serializers.ModelSerializer):
    image_type_name = serializers.CharField(source="image_type.name", read_only=True)

    class Meta:
        model = CroppedImageExtra
        fields = (
            "id",
            "parent",
            "image",
            "image_type",
            "image_type_name",
            "rect_pdf",
            "rect_screen",
            "sort_order",
            "created_at",
            "updated_at",
        )


class CroppedImageExtraWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CroppedImageExtra
        fields = (
            "id",
            "parent",
            "image",
            "image_type",
            "rect_pdf",
            "rect_screen",
            "sort_order",
        )
        read_only_fields = ("id",)


class CroppedImageReadSerializer(serializers.ModelSerializer):
    usage_types = UsageTypeSerializer(many=True, read_only=True)
    image_type_name = serializers.CharField(source="image_type.name", read_only=True)
    question_type_name = serializers.CharField(source="question_type.name", read_only=True)
    source_name = serializers.CharField(source="source.name", read_only=True)
    class_name_name = serializers.CharField(source="class_name.name", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    chapter_name = serializers.CharField(source="chapter.name", read_only=True)
    concept_name = serializers.CharField(source="concept.name", read_only=True)
    topic_name = serializers.CharField(source="topic.name", read_only=True)
    extra_images = CroppedImageExtraReadSerializer(many=True, read_only=True)

    class Meta:
        model = CroppedImage
        fields = (
            "id",
            "image",
            "image_type",
            "image_type_name",
            "extra_images",
            "rect_pdf",
            "rect_screen",
            "class_name",
            "class_name_name",
            "subject",
            "subject_name",
            "chapter",
            "chapter_name",
            "concept",
            "concept_name",
            "topic",
            "topic_name",
            "question_type",
            "question_type_name",
            "difficulty",
            "marks",
            "usage_types",
            "priority",
            "verified",
            "source",
            "source_name",
            "is_active",
            "created_at",
            "updated_at",
        )
