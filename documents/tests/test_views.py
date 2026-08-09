import io

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token

from documents.models import Document, Question, Summary

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
        response = self.client.post("/api/documents/upload/", {"file": self._pdf_upload_file()})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_successful_upload_returns_202(self):
        response = self.client.post("/api/documents/upload/", {"file": self._pdf_upload_file()})
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(Document.objects.count(), 1)
        self.assertEqual(Document.objects.first().owner, self.user)

    def test_rejects_non_pdf_file(self):
        file_obj = SimpleUploadedFile("test.txt", b"some text", content_type="text/plain")
        response = self.client.post("/api/documents/upload/", {"file": file_obj})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Document.objects.count(), 0)