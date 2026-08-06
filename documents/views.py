from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Document, Question
from .serializers import (
    DocumentDetailSerializer,
    DocumentListSerializer,
    DocumentUploadSerializer,
    QuestionSerializer,
)

# Create your views here.

class DocumentUploadView(APIView):
    """
    POST a PDF file under the 'file' field.

    Currently synchronous end-to-end (no Celery yet): saves the Document
    row and returns it immediately with status=pending. Text extraction,
    chunking and summarization will move into Celery tasks in a later step -
    this view will then just enqueue and return 202.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post (self, request):
        serializer = DocumentUploadSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        document = serializer.save()
        return Response(
            DocumentUploadSerializer(document).data,
            status=status.HTTP_201_CREATED,
        )

class DocumentListView(ListAPIView):
    """Documents belonging to the authenticated user."""

    serializer_class = DocumentListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Document.objects.filter(owner=self.request.user)
    
class DocumentDetailView(RetrieveAPIView):
    """
    Detail + status endpoint. Clients poll this until status == 'done'.
    Includes the nested summary once processing completes.
    """

    serializer_class = DocumentDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Document.objects.filter(owner=self.request.user)
    
class QuestionCreateView(APIView):
    """
    POST {"question_text": "..." against a processed document.}

    Only works once the document's status is 'done'. Answering itself will
    be wired up (sync call to the LLM, or a Celery task) later. For
    now this just validates and stores the question.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, document_id):
        try:
            document = Document.objects.get(id=document_id, owner=request.user)
        except Document.DoesNotExist:
            return Response(
                {"detail": "Document not found."}, status=status.HTTP_404_NOT_FOUND
            )

        if document.status != Document.Status.DONE:
            return Response(
                {"detail": "Document is not ready for questions yet."},
                status=status.HTTP_409_CONFLICT,
            )
        
        serializer = QuestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question = Question.objects.create(
            document=document,
            asked_by=request.user,
            question_text=serializer.validated_data["question_text"],
        )
        return Response(
            QuestionSerializer(question).data, status=status.HTTP_201_CREATED
        )