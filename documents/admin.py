from django.contrib import admin

from .models import Chunk, Document, Question, Summary

# Register your models here.

class ChunkInline(admin.TabularInline):
    model = Chunk
    extra = 0
    readonly_fields = ["index", "content"]
    can_delete = False

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["id", "original_filename", "owner", "status", "uploaded_at"]
    list_filter = ["status"]
    search_fields = ["original_filename", "owner__username"]
    inlines = [ChunkInline]

@admin.register(Summary)
class SummaryAdmin(admin.ModelAdmin):
    list_display = ["id", "document", "model_used", "created_at"]

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ["id", "document", "asked_by", "created_at", "answered_at"]
    list_filter = ["document"]