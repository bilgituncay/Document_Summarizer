from django.urls import path

from .views import (
    DocumentDetailView,
    DocumentListView,
    DocumentUploadView,
    QuestionDetailView,
    QuestionListCreateView,
)

app_name = "documents"

urlpatterns = [
    path("documents/", DocumentListView.as_view(), name="document-list"),
    path("documents/upload/", DocumentUploadView.as_view(), name="document-upload"),
    path("documents/<int:pk>/", DocumentDetailView.as_view(), name="document-detail"),
    path("documents/<int:document_id>/questions/", QuestionListCreateView.as_view(), name="question-list-create"),
    path("questions/<int:pk>/", QuestionDetailView.as_view(),name="question-detail"),
]