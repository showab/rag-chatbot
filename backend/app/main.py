from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
import os
from dotenv import load_dotenv

from app.services.rag import RAGService
from app.services.document_processor import DocumentProcessor

load_dotenv()

app = FastAPI(title="RAG Chatbot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

doc_processor = DocumentProcessor()
rag_service = RAGService()


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    sources: List[dict]
    conversation_id: str


@app.get("/")
async def root():
    return {"message": "RAG Chatbot API is running", "status": "healthy"}


@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.endswith('.pdf'):
        raise HTTPException(400, "Only PDF files are allowed")

    file_path = await doc_processor.save_upload(file)
    chunks = await doc_processor.process_pdf(file_path, file.filename)
    await rag_service.add_documents(chunks)

    return {
        "message": f"Successfully processed {file.filename}",
        "chunks": len(chunks),
        "filename": file.filename
    }


@app.post("/chat")
async def chat(request: ChatRequest):
    result = await rag_service.query(
        question=request.message,
        conversation_id=request.conversation_id
    )
    return result


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    async def event_stream():
        async for chunk in rag_service.query_stream(
            question=request.message,
            conversation_id=request.conversation_id
        ):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream"
    )


@app.get("/documents")
async def list_documents():
    return {"documents": doc_processor.list_documents()}


@app.delete("/documents/{filename}")
async def delete_document(filename: str):
    await rag_service.delete_document(filename)
    doc_processor.remove_document(filename)
    return {"message": f"Deleted {filename}"}
