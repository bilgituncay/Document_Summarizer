from unittest.mock import patch
from unittest.mock import MagicMock, patch

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
    
    @patch("documents.tasks.anthropic.Anthropic")
    def test_extraction_creates_chunks_and_triggers_summary(self, mock_anthropic_class):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="A mocked summary.")]
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        document = self._document_with_real_pdf("Hello World, this is a test document.")
        extract_and_chunk_document(document.id, "fake-api-key")

        document.refresh_from_db()
        self.assertEqual(document.status, Document.Status.DONE)
        self.assertEqual(Chunk.objects.filter(document=document).count(), 1)
        self.assertTrue(Summary.objects.filter(document=document).exists())

    def test_missing_document_id_does_not_crash(self):
        extract_and_chunk_document(99999, "fake-api-key")

    def test_missing_file_marks_failed_and_raises(self):
        document = Document.objects.create(
            owner=self.user, file="documents/1/nonexistent.pdf", original_filename="nonexistent.pdf"
        )
        with self.assertRaises(FileNotFoundError):
            extract_and_chunk_document(document.id, "fake-api-key")

        document.refresh_from_db()
        self.assertEqual(document.status, Document.Status.FAILED)
        self.assertNotEqual(document.error_message, "")

    def test_empty_pdf_marks_failed(self):
        document = self._document_with_real_pdf(text="")
        with self.assertRaises(ValueError):
            extract_and_chunk_document(document.id, "fake-api-key")

        document.refresh_from_db()
        self.assertEqual(document.status, Document.Status.FAILED)
        self.assertIn("No extractable text", document.error_message)

class SummarizeDocumentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="julia", password="testpass123")
        self.document = Document.objects.create(owner=self.user, file="documents/1/fake.pdf", original_filename="fake.pdf")
    @patch("documents.tasks.anthropic.Anthropic")
    def test_summarizes_document_with_chunks(self, mock_anthropic_class):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="A mocked summary.")]
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        Chunk.objects.create(document=self.document, index=0, content="Some extracted text.")
        summarize_document(self.document.id, "fake-api-key")

        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.DONE)
        self.assertIsNotNone(self.document.processed_at)
        summary = Summary.objects.get(document=self.document)
        self.assertEqual(summary.content, "A mocked summary.")
        self.assertEqual(summary.model_used, "claude-sonnet-4-5")
        mock_client.messages.create.assert_called_once()

    def test_no_chunks_marks_failed_and_raises(self):
        with self.assertRaises(ValueError):
            summarize_document(self.document.id, "fake-api-key")

        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.FAILED)
        self.assertIn("No chunks found", self.document.error_message)

    @patch("documents.tasks.anthropic.Anthropic")
    def test_rerunning_after_chunks_added_succeeds_and_does_not_duplicate_summary(self, mock_anthropic_class):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="A mocked summary.")]
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client
        
        # Simulates a retry: first attempts fails. (no chunks yet)
        with self.assertRaises(ValueError):
            summarize_document(self.document.id, "fake-api-key")

        # Retry with chunks.
        Chunk.objects.create(document=self.document, index=0, content="Some text.")
        summarize_document(self.document.id, "fake-api-key")

        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.DONE)
        self.assertEqual(Summary.objects.filter(document=self.document).count(), 1)

class AnswerQuestionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="kevin", password="testpass123")
        self.document = Document.objects.create(
            owner=self.user, file="documents/1/fake.pdf", original_filename="fake.pdf", status=Document.Status.DONE
            )
        self.question = Question.objects.create(document=self.document, asked_by=self.user, question_text="What is this?")

    @patch("documents.tasks.anthropic.Anthropic")
    def test_answers_question_with_chunks(self, mock_anthropic_class):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="A mocked answer.")]
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        Chunk.objects.create(document=self.document, index=0, content="Some text.")
        answer_question(self.question.id, "fake-api-key")

        self.question.refresh_from_db()
        self.assertEqual(self.question.answer_text, "A mocked answer.")
        self.assertIsNotNone(self.question.answered_at)
        self.assertEqual(self.question.error_message, "")

    def test_no_chunks_records_error_and_raises(self):
        with self.assertRaises(ValueError):
            answer_question(self.question.id, "fake-api-key")

        self.question.refresh_from_db()
        self.assertEqual(self.question.answer_text, "")
        self.assertIn("no chunks", self.question.error_message.lower())

    @patch("documents.tasks.anthropic.Anthropic")
    def test_error_message_clears_on_successful_retry(self, mock_anthropic_class):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="A mocked answer.")]
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        with self.assertRaises(ValueError):
            answer_question(self.question.id, "fake-api-key")
        self.question.refresh_from_db()
        self.assertNotEqual(self.question.error_message, "")

        Chunk.objects.create(document=self.document, index=0, content="Some text.")
        answer_question(self.question.id, "fake-api-key")

        self.question.refresh_from_db()
        self.assertEqual(self.question.error_message, "")
        self.assertEqual(self.question.answer_text, "A mocked answer.")