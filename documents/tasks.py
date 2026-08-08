import logging

from django.utils import timezone
from celery import shared_task
from pypdf import PdfReader

from .models import Chunk, Document, Summary, Question

logger = logging.getLogger(__name__)

CHUNK_SIZE = 2000

@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def extract_and_chunk_document(self, document_id):
    """
    Extract text from the document's PDF and split it into Chunk rows.
    Triggers the summarization task on success.
    """
    try:
        document = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        logger.error("Document %s not found for extraction", document_id)
        return

    document.status = Document.Status.PROCESSING
    document.save(update_fields=["status"])

    try:
        reader = PdfReader(document.file.path)
        full_text = "\n".join(page.extract_text() or "" for page in reader.pages)

        if not full_text.strip():
            raise ValueError("No extractable text found in PDF (may be scanned/image-based).")

        chunks = [
            full_text[i:i + CHUNK_SIZE]
            for i in range(0, len(full_text), CHUNK_SIZE)
        ]

        Chunk.objects.bulk_create([
            Chunk(document=document, index=idx, content=content)
            for idx, content in enumerate(chunks)
        ])

        summarize_document.delay(document_id)

    except Exception as exc:
        document.status = Document.Status.FAILED
        document.error_message = str(exc)
        document.save(update_fields=["status", "error_message"])
        logger.exception("Extraction failed for document %s", document_id)
        raise self.retry(exc=exc)

@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def summarize_document(self, document_id):
    """
    Generate a summary from a document's chunks and mark it done.

    Currently uses a placecholder instead of a real LLM call.
    """
    try:
        document = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        logger.error("Document %s not found for summarization", document_id)
        return
    
    try:
        chunk_count = document.chunks.count()
        if chunk_count == 0:
            raise ValueError("No chunks found - extraction may have failed.")
        
        # Placeholder - replace with an LLM call.
        placeholder_text = (
            f"[Placeholder summary] This document contains {chunk_count} "
            f"chunk(s) of extracted text. Real summarization not yet wired in."
        )

        Summary.objects.update_or_create(
            document=document,
            defaults={
                "content": placeholder_text,
                "model_used": "placeholder",
            },
        )

        document.status = Document.Status.DONE
        document.processed_at = timezone.now()
        document.save(update_fields=["status", "processed_at"])
    
    except Exception as exc:
        document.status = Document.Status.FAILED
        document.error_message = str(exc)
        document.save(update_fields=["status", "error_message"])
        logger.exception("summarization failed for document %s", document_id)
        raise self.retry(exc=exc)

@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def answer_question(self,question_id):
    """
    Generate an answer to a Question with the document's chunks as context.
    Currently a placeholder - swap for an LLM call.
    """
    try:
        question = Question.objects.select_related("document").get(id=question_id)
    except Question.DoesNotExist:
        logger.error("Question %s not found", question_id)
        return
    
    try:
        chunk_count = question.document.chunks.count()
        if chunk_count == 0:
            raise ValueError("Document has no chunks to answer from.")
        
        # Placeholder - replace with an LLM call.
        placeholder_answer = (
            f"[Placeholder answer] with {chunk_count} chunk(s) of "
            f"'{question.document.original_filename}' as context."
        )

        question.answer_text = placeholder_answer
        question.model_used = "placeholder"
        question.answered_at = timezone.now()
        question.error_message = ""
        question.save(update_fields=["answer_text", "model_used", "answered_at", "error_message"])
    
    except Exception as exc:
        question.error_message = str(exc)
        question.save(update_fields=["error_message"])
        logger.exception("Answering failed for question %s", question_id)
        raise self.retry(exc=exc)