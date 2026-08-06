from django.conf import settings
from rest_framework import serializers

from .models import Chunk, Document, Question, Summary

class ChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chunk
        fields = ["id", "index", "content"]

class SummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Summary
        fields = ["id", "content", "model_used", "created_at"]

class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = [
            "id",
            "question_text",
            "answer_text",
            "model_used",
            "created_at",
            "answered_at",
        ]
        read_only_fields = ["answer_text", "model_used", "created_at", "answered_at"]

class DocumentListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""

    class Meta:
        model = Document
        fields = ["id", "original_filename", "status", "uploaded_at", "processed_at"]

class DocumentDetailSerializer(serializers.ModelSerializer):
    """Full serializer including nested summary, for detail/status views."""

    summary = SummarySerializer(read_only=True)

    class Meta:
        model = Document
        fields = [
            "id",
            "original_filename",
            "status",
            "error_message",
            "uploaded_at",
            "processed_at",
            "summary",
        ]

class DocumentUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ["id", "original_filename", "status", "uploaded_at"]
        read_only_fields = ["id", "original_filename", "status", "uploaded_at"]

    def validate_file(self,value):
        max_size = getattr(settings, "MAX_DOCUMENT_UPLOAD_SIZE", 10 * 1024 * 1024)
        if value.size > max_size:
            raise serializers.ValidationError(
                f"File too large. Max size is {max_size // (1024 * 1024)}MB."
            )
        if not value.name.lower().endswith(".pdf"):
            raise serializers.ValidationError("Only PDF files are supported.")
        return value
    
    def create(self, validated_data):
        validated_data["original_filename"] = validated_data["file"].name
        validated_data["owner"] = self.context["request"].user
        return super().create(validated_data)