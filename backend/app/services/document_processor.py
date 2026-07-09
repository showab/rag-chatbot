"""
Document Processor — PDF parsing, text extraction, and chunking.
"""

import os
import uuid
import shutil
from typing import List

from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
import pdfplumber

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads")


class DocumentProcessor:
    """Handles PDF uploads, text extraction, and smart chunking."""

    def __init__(self):
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len,
        )

    async def save_upload(self, file) -> str:
        """Save an uploaded file to disk and return the path."""
        safe_filename = f"{uuid.uuid4().hex}_{file.filename}"
        file_path = os.path.join(UPLOAD_DIR, safe_filename)

        content = await file.read()
        with open(file_path, 'wb') as f:
            f.write(content)

        return file_path

    async def process_pdf(self, file_path: str, original_filename: str) -> List[Document]:
        """Extract text from PDF, chunk it, and return LangChain Documents."""
        full_text = ""
        page_texts = []

        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                if text:
                    # Also try extracting tables
                    tables = page.extract_tables()
                    table_text = ""
                    for table in tables:
                        if table:
                            table_text += "\n".join([
                                " | ".join([str(cell or "") for cell in row])
                                for row in table
                            ]) + "\n"

                    page_content = text + ("\n\n[TABLE]\n" + table_text if table_text else "")
                    full_text += f"\n--- Page {page_num} ---\n{page_content}"
                    page_texts.append((page_num, page_content))

        if not full_text.strip():
            return []

        # Create chunks with page metadata
        chunks = []
        for page_num, page_content in page_texts:
            page_chunks = self.text_splitter.split_text(page_content)
            for chunk in page_chunks:
                chunks.append(Document(
                    page_content=chunk,
                    metadata={
                        "source": original_filename,
                        "page": page_num,
                        "chunk_id": str(uuid.uuid4().hex)[:8]
                    }
                ))

        return chunks

    def list_documents(self) -> List[dict]:
        """List all uploaded PDF files."""
        docs = []
        if os.path.exists(UPLOAD_DIR):
            for f in os.listdir(UPLOAD_DIR):
                if f.endswith('.pdf'):
                    # Strip the uuid prefix to get original name
                    parts = f.split('_', 1)
                    original_name = parts[1] if len(parts) > 1 else f
                    docs.append({
                        "filename": original_name,
                        "stored_name": f
                    })
        return docs

    def remove_document(self, filename: str):
        """Remove a document's file from disk."""
        if os.path.exists(UPLOAD_DIR):
            for f in os.listdir(UPLOAD_DIR):
                if f.endswith(f"_{filename}"):
                    os.remove(os.path.join(UPLOAD_DIR, f))
