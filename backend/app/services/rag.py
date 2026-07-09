"""
RAG Service — Core Retrieval-Augmented Generation engine.
Handles embedding, vector storage, retrieval, and LLM querying.
"""

import os
import json
import uuid
import asyncio
from typing import List, Dict, Optional, AsyncGenerator

from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from dotenv import load_dotenv

load_dotenv()

CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "chroma_db")
CONVERSATIONS_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "conversations.json")


class RAGService:
    """Core RAG pipeline: ingestion, retrieval, generation with citations."""

    def __init__(self):
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3, streaming=True)
        self.vectorstore: Optional[Chroma] = None
        self._init_vectorstore()
        self.conversations = self._load_conversations()

        self.qa_prompt = PromptTemplate(
            template="""You are a helpful AI assistant that answers questions based on the provided context documents.
Use ONLY the context below to answer. If you cannot answer from the context, say "I don't have enough information from the uploaded documents to answer that question."

Always cite your sources using [Source: filename] notation. Include relevant quotes from the context.

Context:
{context}

Question: {question}

Helpful Answer (with source citations):""",
            input_variables=["context", "question"]
        )

    def _init_vectorstore(self):
        """Initialize or load ChromaDB vector store."""
        os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
        try:
            self.vectorstore = Chroma(
                persist_directory=CHROMA_PERSIST_DIR,
                embedding_function=self.embeddings,
                collection_name="rag_documents"
            )
        except Exception:
            self.vectorstore = Chroma(
                persist_directory=CHROMA_PERSIST_DIR,
                embedding_function=self.embeddings,
                collection_name="rag_documents"
            )

    def _load_conversations(self) -> Dict:
        """Load conversation history from disk."""
        if os.path.exists(CONVERSATIONS_FILE):
            with open(CONVERSATIONS_FILE, 'r') as f:
                return json.load(f)
        return {}

    def _save_conversations(self):
        """Persist conversation history to disk."""
        with open(CONVERSATIONS_FILE, 'w') as f:
            json.dump(self.conversations, f, indent=2)

    async def add_documents(self, chunks: List[Document]):
        """Add document chunks to the vector store."""
        if not chunks:
            return
        texts = [chunk.page_content for chunk in chunks]
        metadatas = [chunk.metadata for chunk in chunks]
        self.vectorstore.add_texts(texts=texts, metadatas=metadatas)

    async def query(self, question: str, conversation_id: Optional[str] = None) -> Dict:
        """Query the RAG system with citation-backed results."""
        if not self.vectorstore:
            return {"answer": "No documents uploaded yet.", "sources": [], "conversation_id": conversation_id}

        retriever = self.vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 5}
        )

        # Retrieve relevant documents
        docs = retriever.get_relevant_documents(question)

        # Build context
        context_parts = []
        sources = []
        for i, doc in enumerate(docs):
            source = doc.metadata.get("source", "unknown")
            page = doc.metadata.get("page", "N/A")
            context_parts.append(f"[Document {i+1}] Source: {source} (Page {page})\n{doc.page_content}")
            sources.append({
                "filename": source,
                "page": page,
                "excerpt": doc.page_content[:200] + "..."
            })

        context = "\n\n".join(context_parts)

        # Include conversation history
        history = ""
        if conversation_id and conversation_id in self.conversations:
            history_msgs = self.conversations[conversation_id][-6:]  # last 3 exchanges
            history = "\n".join([
                f"User: {msg['user']}\nAssistant: {msg['assistant']}"
                for msg in history_msgs
            ])

        full_question = question
        if history:
            full_question = f"Previous conversation:\n{history}\n\nCurrent question: {question}"

        # Generate answer
        prompt = self.qa_prompt.format(context=context, question=full_question)
        response = await self.llm.ainvoke(prompt)
        answer = response.content

        # Save conversation
        cid = conversation_id or str(uuid.uuid4())
        if cid not in self.conversations:
            self.conversations[cid] = []
        self.conversations[cid].append({"user": question, "assistant": answer})
        self._save_conversations()

        return {
            "answer": answer,
            "sources": sources,
            "conversation_id": cid
        }

    async def query_stream(
        self, question: str, conversation_id: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """Stream the RAG answer token by token via SSE."""
        if not self.vectorstore:
            yield json.dumps({"type": "error", "content": "No documents uploaded yet."})
            return

        retriever = self.vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 5}
        )

        docs = retriever.get_relevant_documents(question)

        # Send sources first
        sources = []
        context_parts = []
        for i, doc in enumerate(docs):
            source = doc.metadata.get("source", "unknown")
            page = doc.metadata.get("page", "N/A")
            context_parts.append(f"[Document {i+1}] Source: {source} (Page {page})\n{doc.page_content}")
            sources.append({
                "filename": source,
                "page": page,
                "excerpt": doc.page_content[:200] + "..."
            })

        yield json.dumps({"type": "sources", "content": sources}) + "\n"

        context = "\n\n".join(context_parts)

        # Include history
        history = ""
        if conversation_id and conversation_id in self.conversations:
            history_msgs = self.conversations[conversation_id][-6:]
            history = "\n".join([
                f"User: {msg['user']}\nAssistant: {msg['assistant']}"
                for msg in history_msgs
            ])

        full_question = question
        if history:
            full_question = f"Previous conversation:\n{history}\n\nCurrent question: {question}"

        prompt = self.qa_prompt.format(context=context, question=full_question)

        # Stream answer
        full_answer = ""
        async for chunk in self.llm.astream(prompt):
            if chunk.content:
                full_answer += chunk.content
                yield json.dumps({"type": "token", "content": chunk.content}) + "\n"

        # Save conversation
        cid = conversation_id or str(uuid.uuid4())
        if cid not in self.conversations:
            self.conversations[cid] = []
        self.conversations[cid].append({"user": question, "assistant": full_answer})
        self._save_conversations()

        yield json.dumps({"type": "done", "conversation_id": cid}) + "\n"

    async def delete_document(self, filename: str):
        """Delete all chunks for a given document from the vector store."""
        if self.vectorstore:
            collection = self.vectorstore._collection
            try:
                collection.delete(where={"source": filename})
            except Exception:
                pass
