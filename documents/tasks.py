import logging
import anthropic

from django.utils import timezone
from celery import shared_task
from pypdf import PdfReader

from .models import Chunk, Document, Summary, Question

logger = logging.getLogger(__name__)

CHUNK_SIZE = 2000

@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def extract_and_chunk_document(self, document_id, api_key):
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

        summarize_document.delay(document_id, api_key)

    except Exception as exc:
        document.status = Document.Status.FAILED
        document.error_message = str(exc)
        document.save(update_fields=["status", "error_message"])
        logger.exception("Extraction failed for document %s", document_id)
        raise self.retry(exc=exc)

@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def summarize_document(self, document_id, api_key):
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
        chunks = list(document.chunks.order_by("index").values_list("content", flat=True))
        if not chunks:
            raise ValueError("No chunks found - extraction may have failed.")
        
        full_text = "\n".join(chunks)
        model_name = "claude-sonnet-4-5"

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model_name,
            max_tokens=500,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Summarize the following document in a few concise "
                        f"paragraphs:\n\n{full_text}"
                    ),
                }
            ],
        )
        summary_text = response.content[0].text

        Summary.objects.update_or_create(
            document=document,
            defaults={"content": summary_text, "model_used": model_name},
        )

        document.status = Document.Status.DONE
        document.processed_at = timezone.now()
        document.save(update_fields=["status", "processed_at"])

    except anthropic.AuthenticationError as exc:
        document.status = Document.Status.FAILED
        document.error_message = "Invalid Anthropic API key."
        document.save(update_fields=["status", "error_message"])
        logger.exception("Authentication failed for document %s", document_id)
        # No retries - a bad key will always fail.

    except Exception as exc:
        document.status = Document.Status.FAILED
        document.error_message = str(exc)
        document.save(update_fields=["status", "error_message"])
        logger.exception("summarization failed for document %s", document_id)
        raise self.retry(exc=exc)

@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def answer_question(self,question_id, api_key):
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
        chunks = list(
            question.document.chunks.order_by("index").values_list("content", flat=True)
        )
        if not chunks:
            raise ValueError("Document has no chunks to answer from.")
        
        full_text = "\n".join(chunks)
        model_name = "claude-sonnet-4-5"

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model_name,
            max_tokens=500,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Using the following document, answer this question: "
                        f"{question.question_text}\n\nDocument:\n{full_text}"
                    ),
                }
            ],
        )
        answer_text = response.content[0].text

        question.answer_text = answer_text
        question.model_used = model_name
        question.answered_at = timezone.now()
        question.error_message = ""
        question.save(update_fields=["answer_text", "model_used", "answered_at", "error_message"])

    except anthropic.AuthenticationError:
        question.error_message = "Invalid Anthropic API key."
        question.save(update_fields=["error_message"])
        logger.exception("Authentication failed for question %s", question_id)
        # No retries.

    except Exception as exc:
        question.error_message = str(exc)
        question.save(update_fields=["error_message"])
        logger.exception("Answering failed for question %s", question_id)
        raise self.retry(exc=exc)