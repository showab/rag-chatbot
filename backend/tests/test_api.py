import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.main import app

client = TestClient(app)


def test_root():
    """Test health check endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_list_documents_empty():
    """Test listing documents when none are uploaded."""
    response = client.get("/documents")
    assert response.status_code == 200
    assert "documents" in response.json()


def test_upload_non_pdf():
    """Test uploading a non-PDF file is rejected."""
    response = client.post(
        "/upload",
        files={"file": ("test.txt", b"hello world", "text/plain")}
    )
    assert response.status_code == 400


@patch("app.services.rag.RAGService.query")
def test_chat_endpoint(mock_query):
    """Test the chat endpoint returns proper response format."""
    mock_query.return_value = {
        "answer": "Test answer",
        "sources": [{"filename": "test.pdf", "page": 1, "excerpt": "test..."}],
        "conversation_id": "test-123"
    }

    response = client.post("/chat", json={
        "message": "What is this about?",
        "conversation_id": None
    })

    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert "sources" in data
    assert "conversation_id" in data
