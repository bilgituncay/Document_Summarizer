import logging

from celery import shared_task
from pypdf import PdfReader

from .models import Chunk, Document

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

    except Exception as exc:
        document.status = Document.Status.FAILED
        document.error_message = str(exc)
        document.save(update_fields=["status", "error_message"])
        logger.exception("Extraction failed for document %s", document_id)
        raise self.retry(exc=exc)