import os
import uuid

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models

def document_upload_path(instance, filename):
    """Namespace uploads by owner id and a random name to avoid collisions."""
    ext = os.path.splitext(filename)[1]
    return f"documents/{instance.owner_id}/{uuid.uuid4()}{ext}"

# Create your models here.

class Document(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents"
    )

    file = models.FileField(
        upload_to=document_upload_path,
        validators=[FileExtensionValidator(allowed_extensions=["pdf"])],
    )
    original_filename = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    error_message = models.TextField(blank=True, default="")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.original_filename} ({self.status})"

class Chunk(models.Model):
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    index = models.PositiveIntegerField()
    content = models.TextField()

    class Meta:
        ordering = ["index"]
        unique_together = ("document", "index")

    def __str__(self):
        return f"Chunk {self.index} of document {self.document_id}"

class Summary(models.Model):
    document = models.OneToOneField(
        Document,
        on_delete=models.CASCADE,
        related_name="summary",
    )
    content = models.TextField()
    model_used = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Summary for document {self.document_id}"

class Question(models.Model):
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    asked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="questions_asked",
    )
    question_text = models.TextField()
    answer_text = models.TextField(blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    model_used = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Q on document {self.document_id}: {self.question_text[:50]}"