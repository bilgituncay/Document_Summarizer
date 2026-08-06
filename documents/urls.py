from django.urls import path

from .views import (
    DocumentDetailView,
    DocumentListView,
    DocumentUploadView,
    QuestionCreateView,
)

app_name = "documents"

urlpatterns = [
    path("documents/", DocumentListView.as_view(), name="document-list"),
    path("documents/upload/", DocumentUploadView.as_view(), name="document-upload"),
    path("documents/<int:pk>/", DocumentListView.as_view(), name="document-detail"),
    path("documents/<int:document_id>/questions/", QuestionCreateView.as_view(), name="question-create"),
]