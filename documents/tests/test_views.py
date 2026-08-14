import io

from unittest.mock import MagicMock, patch
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token

from documents.models import Document, Question, Summary, Chunk

def make_pdf_bytes(text="Hello World"):
    """Minimal but structurally valid single-page PDF with real extractable text."""
    objects = []
    objects.append(b"<</Type/Catalog/Pages 2 0 R>>")
    objects.append(b"<</Type/Pages/Kids[3 0 R]/Count 1>>")
    objects.append(
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]"
        b"/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>"
    )
    objects.append(b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>")
    stream_content = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode()
    objects.append(
        b"<</Length " + str(len(stream_content)).encode() + b">>\nstream\n"
        + stream_content + b"\nendstream"
    )

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj".encode() + obj + b"endobj\n"

    xref_offset = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010} 00000 n \n".encode()
    out += (
        f"trailer<</Size {len(objects) + 1}/Root 1 0 R>>\n"
        f"startxref\n{xref_offset}\n%%EOF"
    ).encode()
    return bytes(out)

class DocumentAPITestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="grace", password="testpass123")
        self.other_user = User.objects.create_user(username="henry", password="testpass123")
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def _pdf_upload_file(self, name="test.pdf"):
        return SimpleUploadedFile(name, make_pdf_bytes(), content_type="application/pdf")

class DocumentUploadViewTests(DocumentAPITestCase):
    def test_upload_requires_authentication(self):
        self.client.credentials()
        response = self.client.post(
            "/api/documents/upload/",
            {"file": self._pdf_upload_file()},
            HTTP_X_ANTHROPIC_API_KEY="fake-api-key",
            )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch("documents.tasks.anthropic.Anthropic")
    def test_successful_upload_returns_202(self, mock_anthropic_class):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="A mocked summary.")]
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client
        
        response = self.client.post(
            "/api/documents/upload/",
            {"file": self._pdf_upload_file()},
            HTTP_X_ANTHROPIC_API_KEY="fake-api-key",
            )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(Document.objects.count(), 1)
        self.assertEqual(Document.objects.first().owner, self.user)

    def test_rejects_non_pdf_file(self):
        file_obj = SimpleUploadedFile("test.txt", b"some text", content_type="text/plain")
        response = self.client.post(
            "/api/documents/upload/",
            {"file": file_obj},
            HTTP_X_ANTHROPIC_API_KEY="fake-api-key",
            )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Document.objects.count(), 0)

    def test_upload_requires_api_key(self):
        response = self.client.post(
            "/api/documents/upload/", {"file": self._pdf_upload_file()}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Document.objects.count(), 0)

class DocumentListViewTests(DocumentAPITestCase):
    def test_lists_only_own_documents(self):
        Document.objects.create(
            owner=self.user, file="documents/1/mine.pdf", original_filename="mine.pdf"
        )
        Document.objects.create(
            owner=self.other_user, file="documents/2/theirs.pdf", original_filename="theirs.pdf"
        )
        response = self.client.get("/api/documents/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["original_filename"], "mine.pdf")


class DocumentDetailViewTests(DocumentAPITestCase):
    def setUp(self):
        super().setUp()
        self.own_document = Document.objects.create(
            owner=self.user, file="documents/1/mine.pdf", original_filename="mine.pdf"
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

    def test_summary_null_before_processing(self):
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
            file="documents/1/done.pdf",
            original_filename="done.pdf",
            status=Document.Status.DONE,
        )
        Chunk.objects.create(document=self.done_document, index=0, content="Some extracted text.")
        Summary.objects.create(
            document=self.done_document, content="A summary.", model_used="placeholder"
        )

    def test_cannot_ask_question_on_pending_document(self):
        response = self.client.post(
            f"/api/documents/{self.pending_document.id}/questions/",
            {"question_text": "What is this?"},
            HTTP_X_ANTHROPIC_API_KEY="fake-api-key",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Question.objects.count(), 0)

    @patch("documents.tasks.anthropic.Anthropic")
    def test_can_ask_question_on_done_document(self, mock_anthropic_class):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="A mocked answer.")]
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        response = self.client.post(
            f"/api/documents/{self.done_document.id}/questions/",
            {"question_text": "What is this about?"},
            HTTP_X_ANTHROPIC_API_KEY="fake-api-key",
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(Question.objects.count(), 1)
        question = Question.objects.first()
        self.assertEqual(question.asked_by, self.user)
        self.assertEqual(question.answer_text, "A mocked answer.")
        self.assertIsNotNone(question.answered_at)

    def test_lists_only_questions_for_that_document(self):
        Question.objects.create(
            document=self.done_document, asked_by=self.user, question_text="Q1"
        )
        other_done_document = Document.objects.create(
            owner=self.user,
            file="documents/1/other.pdf",
            original_filename="other.pdf",
            status=Document.Status.DONE,
        )
        Question.objects.create(
            document=other_done_document, asked_by=self.user, question_text="Q2"
        )
        response = self.client.get(f"/api/documents/{self.done_document.id}/questions/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["question_text"], "Q1")

    def test_cannot_ask_question_on_other_users_document(self):
        other_document = Document.objects.create(
            owner=self.other_user,
            file="documents/2/theirs.pdf",
            original_filename="theirs.pdf",
            status=Document.Status.DONE,
        )
        response = self.client.post(
            f"/api/documents/{other_document.id}/questions/",
            {"question_text": "Sneaky question"},
            HTTP_X_ANTHROPIC_API_KEY="fake-api-key",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class QuestionDetailViewTests(DocumentAPITestCase):
    def setUp(self):
        super().setUp()
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
            document=self.other_document, asked_by=self.other_user, question_text="Their question"
        )

    def test_can_retrieve_own_question(self):
        response = self.client.get(f"/api/questions/{self.question.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["question_text"], "What is this?")

    def test_cannot_retrieve_other_users_question(self):
        response = self.client.get(f"/api/questions/{self.other_question.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)