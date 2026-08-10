from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from documents.models import Chunk, Document, Question, Summary
from documents.tasks import answer_question, extract_and_chunk_document, summarize_document
from documents.tests.test_views import make_pdf_bytes

class ExtractAndChunkDocumentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ivan",password="testpass123")

    def _document_with_real_pdf(self, text="Hello World"):
        from django.core.files.base import ContentFile
        document = Document(owner=self.user, original_filename="test.pdf")
        document.file.save("test.pdf", ContentFile(make_pdf_bytes(text)), save=True)
        return document
    
    def test_extraction_creates_chunks_and_triggers_summary(self):
        document = self._document_with_real_pdf("Hello World, this is a test document.")
        extract_and_chunk_document(document.id)

        document.refresh_from_db()
        self.assertEqual(document.status, Document.Status.DONE)
        self.assertEqual(Chunk.objects.filter(document=document).count(), 1)
        self.assertTrue(Summary.objects.filter(document=document).exists())

    def test_missing_document_id_does_not_crash(self):
        extract_and_chunk_document(99999)

    def test_missing_file_marks_failed_and_raises(self):
        document = Document.objects.create(
            owner=self.user, file="documents/1/nonexistent.pdf", original_filename="nonexistent.pdf"
        )
        with self.assertRaises(FileNotFoundError):
            extract_and_chunk_document(document.id)

        document.refresh_from_db()
        self.assertEqual(document.status, Document.Status.FAILED)
        self.assertNotEqual(document.error_message, "")

    def test_empty_pdf_marks_failed(self):
        document = self._document_with_real_pdf(text="")
        with self.assertRaises(ValueError):
            extract_and_chunk_document(document.id)

        document.refresh_from_db()
        self.assertEqual(document.status, Document.Status.FAILED)
        self.assertIn("No extractable text", document.error_message)