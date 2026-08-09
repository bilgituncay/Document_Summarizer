from unittest.mock import MagicMock

from django.contrib.auth.models import User
from django.test import TestCase,RequestFactory

from documents.models import Document
from documents.serializers import DocumentUploadSerializer

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