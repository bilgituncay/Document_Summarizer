from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase

from documents.models import Chunk, Document, Question, Summary

class DocumentModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="testpass123")
        self.document = Document.objects.create(
            owner=self.user,
            file="documents/1/fake.pdf",
            original_filename="fake.pdf"
        )

    def test_default_status_is_pending(self):
        self.assertEqual(self.document.status, Document.Status.PENDING)

    def test_str_representation(self):
        self.assertEqual(str(self.document), "fake.pdf (pending)")

    def test_ordering_is_newest_first(self):
        second_document = Document.objects.create(
            owner=self.user, file="documents/1/older.pdf", original_filename="older.pdf"
        )
        documents = list(Document.objects.all())
        self.assertEqual(documents[0], second_document)

class ChunkModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="bob", password="testpass123")
        self.document = Document.objects.create(
            owner=self.user, file="documents/1/fake.pdf", original_filename="fake.pdf"     
        )

    def test_str_representation(self):
        chunk = Chunk.objects.create(document=self.document, index=0, content="hello")
        self.assertEqual(str(chunk), f"Chunk 0 of document {self.document.id}")

    def test_unique_together_document_and_index(self):
        Chunk.objects.create(document=self.document, index=0, content="first")
        with self.assertRaises(IntegrityError):
            Chunk.objects.create(document=self.document, index=0, content="duplicate")

    def test_ordering_by_index(self):
        Chunk.objects.create(document=self.document, index=2, content="third")
        Chunk.objects.create(document=self.document, index=0, content="first")
        Chunk.objects.create(document=self.document, index=1, content="second")
        contents = [c.content for c in self.document.chunks.all()]
        self.assertEqual(contents, ["first", "second", "third"])

class SummaryModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="carol", password="testpass123")
        self.document = Document.objects.create(
            owner=self.user, file="documents/1/fake.pdf", original_filename="fake.pdf"
        )

    def test_one_to_one_constraint(self):
        Summary.objects.create(document=self.document, content="summary 1", model_used="test")
        with self.assertRaises(IntegrityError):
            Summary.objects.create(document=self.document, content="summary 2", model_used="test")
        
class QuestionModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="dave", password="test123")
        self.document = Document.objects.create(
            owner=self.user, file="documents/1/fake.pdf", original_filename="fake.pdf"
        )

    def test_defaults_to_unanswered(self):
        question = Question.objects.create(
            document=self.document, asked_by=self.user, question_text="What is this?"
        )
        self.assertEqual(question.answer_text, "")
        self.assertEqual(question.error_message, "")
        self.assertIsNone(question.answered_at)