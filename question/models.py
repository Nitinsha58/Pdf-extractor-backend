from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver

class ClassName(models.Model):
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
    
class Subject(models.Model):
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
    

class Chapter(models.Model):
    name = models.CharField(max_length=255)
    class_name = models.ForeignKey(ClassName, on_delete=models.CASCADE, related_name="chapters")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="chapters")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.class_name} • {self.subject})"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["name", "class_name", "subject"],
                name="uniq_chapter_per_class_subject",
            )
        ]


class Concept(models.Model):
    name = models.CharField(max_length=255)
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name="concepts")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.chapter})"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["name", "chapter"],
                name="uniq_concept_per_chapter",
            )
        ]


class Topic(models.Model):
    name = models.CharField(max_length=255)
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name="topics")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.concept})"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["name", "concept"],
                name="uniq_topic_per_concept",
            )
        ]

class ImageType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class QuestionType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class UsageType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class Sources(models.Model):
    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class CroppedImage(models.Model):
    DIFFICULTY_CHOICES = [
        ("easy", "Easy"),
        ("medium", "Medium"),
        ("hard", "Hard"),
    ]

    image = models.ImageField(upload_to="cropped/")

    image_type = models.ForeignKey(
        ImageType,
        on_delete=models.PROTECT,
        related_name="cropped_images",
    )

    rect_pdf = models.JSONField(default=dict)
    rect_screen = models.JSONField(default=dict)

    class_name = models.ForeignKey(ClassName, on_delete=models.CASCADE, related_name="cropped_images")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="cropped_images")
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name="cropped_images")
    concept = models.ForeignKey(
        Concept,
        on_delete=models.SET_NULL,
        related_name="cropped_images",
        null=True,
        blank=True,
    )
    topic = models.ForeignKey(
        Topic,
        on_delete=models.SET_NULL,
        related_name="cropped_images",
        null=True,
        blank=True,
    )

    question_type = models.ForeignKey(
        QuestionType,
        on_delete=models.SET_NULL,
        related_name="cropped_images",
        null=True,
        blank=True,
    )
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default="easy")
    marks = models.IntegerField(default=1)
    usage_types = models.ManyToManyField(
        UsageType,
        through="QuestionUsage",
        related_name="cropped_images",
        blank=True,
    )
    priority = models.IntegerField(null=True, blank=True)
    verified = models.BooleanField(default=False)
    source = models.ForeignKey(
        Sources,
        on_delete=models.SET_NULL,
        related_name="cropped_images",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        concept = self.concept or "(no concept)"
        return (
            f"Q#{self.id} • "
            f"{self.class_name} / {self.subject} / {self.chapter} / {concept}"
        )


class QuestionUsage(models.Model):
    question = models.ForeignKey(CroppedImage, on_delete=models.CASCADE, related_name="usage_links")
    usage_type = models.ForeignKey(UsageType, on_delete=models.CASCADE, related_name="question_usage_links")

    class Meta:
        unique_together = ("question", "usage_type")

    def __str__(self):
        return f"{self.question_id} → {self.usage_type}"


@receiver(post_delete, sender=CroppedImage)
def delete_cropped_image_file(sender, instance, **kwargs):
    """Delete the underlying file when the CroppedImage row is deleted."""
    try:
        file_field = instance.image
        if file_field and getattr(file_field, "name", None):
            file_field.delete(save=False)
    except Exception:
        # Avoid breaking deletes if file is already gone or storage errors occur
        pass