from unittest.mock import MagicMock

from django.contrib.auth.models import User
from django.test import TestCase,RequestFactory

from documents.models import Document, Summary, Question
from documents.serializers import DocumentUploadSerializer, DocumentDetailSerializer

class DocumentUploadSerializerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="eve", password="testpass123")
        self.request = RequestFactory().post("/api/documents/upload")
        self.request.user = self.user

    def _fake_file(self,name="test.pdf", size=1024):
        fake_file = MagicMock()
        fake_file.name = name
        fake_file.size = size
        return fake_file
    
    def test_rejects_non_pdf_extension(self):
        serializer = DocumentUploadSerializer(
            data={"file": self._fake_file(name="test.txt")},
            context={"request": self.request},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("file", serializer.errors)

    def test_rejects_oversized_file(self):
        oversized = 11 * 1024 * 1024
        serializer = DocumentUploadSerializer(
            data={"file": self._fake_file(size=oversized)},
            context={"request": self.request},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("file", serializer.errors)

class DocumentDetailSerializerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="frank", password="testpass123")
        self.document = Document.objects.create(
            owner=self.user, file="documents/1/fake.pdf", original_filename="fake.pdf"
        )

    def test_summary_is_null_when_unprocessed(self):
        serializer = DocumentDetailSerializer(self.document)
        self.assertIsNone(serializer.data["summary"])

    def test_summary_is_populated_when_present(self):
        Summary.objects.create(
            document=self.document, content="A test summary.", model_used="placeholder"
        )
        serializer = DocumentDetailSerializer(self.document)
        self.assertEqual(serializer.data["summary"]["content"], "A test summary.")
        self.assertEqual(serializer.data["summary"]["model_used"], "placeholder")

class DocumentListViewTests(DocumentAPITestCase):
    def test_lists_only_own_documents(self):
        Document.objects.create(owner=self.user, file="documents/1/mine.pdf", original_filename="mine.pdf")
        Document.objects.create(owner=self.other_user, file="documents/2/theirs.pdf", original_filename="theirs.pdf")
        response = self.client.get("/api/documents/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["original_filename"])

class DocumentDetailViewTests(DocumentAPITestCase):
    def setUp(self):
        super().setUp()
        self.own_document = Document.objects.create(
            owner=self.user,file="documents/1/mine.pdf", original_filename="mine.pdf"
            )
        self.other_document = Document.objects.create(
            owner=self.other_user, file="documents/2/theirs.pdf", original_filename="theirs.pdf"
        )

    def test_can_retrieve_own_document(self):
        response = self.client.get(f"/api/documents/{self.own_document.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["original_filename"], "mine.pdf")

    def test_cannot_retrieve_other_users_document(self):
        response = self.client.get(f"/api/documents/{self.other_document.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_summary_null_before_passing(self):
        response = self.client.get(f"/api/documents/{self.own_document.id}/")
        self.assertIsNone(response.data["summary"])

class QuestionListCreateViewTests(DocumentAPITestCase):
    def setUp(self):
        super().setUp()
        self.pending_document = Document.objects.create(
            owner=self.user, file="documents/1/pending.pdf", original_filename="pending.pdf"
        )
        self.done_document = Document.objects.create(
            owner=self.user,
            file="documents/1/done.pdf"
            original_filename="done.pdf"
            status=Document.status.DONE,
        )
        Summary.objects.create(
            document=self.done_document, content="A summary.", model_user="placeholder"
        )
    
    def test_cannot_ask_question_on_pending_document(self):
        response = self.client.post(
            f"/api/documents/{self.pending_document.id}/questions/",
            {"question_text": "What is this?"}
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Question.objects.count(), 0)

    def test_can_ask_question_on_done_document(self):
        response = self.client.post(
            f"/api/documents/{self.done_document.id}/questions/",
            {"question_text": "What is this about?"},
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(Question.objects.count(), 0)
        question = Question.objects.first()
        self.assertEqual(question.asked_by, self.user)
        self.assertNotEqual(question.answer_text, "")
        self.assertIsNotNone(question.answered_at)

    def test_lists_only_questions_for_that_document(self):
        Question.objects.create(
            document=self.done_document, asked_by=self.user, question_text="Q1"
        )
        other_done_document = Document.objects.create(
            owner=self.user,
            file="documents/1/other.pdf",
            oriiginal_filename="other.pdf",
            status=Document.Status.DONE,
        )
        Question.objects.create(
            document=other_done_document, asked_by=self.user, question_text="Q2"
        )
        response = self.client.get(f"/api/documents/{self.done_document.id}/questions/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["question_text"], "Q2")

    def test_cannot_ask_question_on_other_users_document(self):
        other_document = Document.objects.create(
            owner=self.other_user,
            file="documents/2//theirs.pdf",
            original_filename="theirs.pdf",
            status=Document.Status.DONE,
        )
        response = self.client.post(
            f"/api/documents/{other_document.id}/questions/",
            {"question_text": "Sneaky question"},
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

class QuestionDetailViewTests(DocumentAPITestCase):
    def setUp(self):
        super().setup()
        self.document = Document.objects.create(
            owner=self.user,
            file="documents/1/done.pdf",
            original_filename="done.pdf",
            status=Document.Status.DONE,
        )
        self.question = Question.objects.create(
            document=self.document, asked_by=self.user, question_text="What is this?"
        )
        self.other_document = Document.objects.create(
            owner=self.other_user,
            file="documents/2/theirs.pdf",
            original_filename="theirs.pdf",
            status=Document.Status.DONE,
        )
        self.other_question = Question.objects.create(
            document=self.other_document, asked_by=self.other_user, question_text="Their question."
        )
    
    def test_can_retrieve_own_question(self):
        response = self.client.get(f"/api/questions/{self.question.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["question_text"], "What is this?")

    def test_cannot_retrieve_other_users_question(self):
        response = self.client.get(f"/api/questions/{self.other_question.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)