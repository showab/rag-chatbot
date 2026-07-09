import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { useDropzone } from 'react-dropzone';
import ReactMarkdown from 'react-markdown';
import './App.css';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [documents, setDocuments] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [showSidebar, setShowSidebar] = useState(true);
  const [uploading, setUploading] = useState(false);
  const chatEndRef = useRef(null);

  useEffect(() => {
    fetchDocuments();
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const fetchDocuments = async () => {
    try {
      const res = await axios.get(`${API_URL}/documents`);
      setDocuments(res.data.documents);
    } catch (err) {
      console.error('Failed to fetch documents:', err);
    }
  };

  const onDrop = async (acceptedFiles) => {
    setUploading(true);
    for (const file of acceptedFiles) {
      const formData = new FormData();
      formData.append('file', file);
      try {
        await axios.post(`${API_URL}/upload`, formData);
        fetchDocuments();
      } catch (err) {
        console.error(`Failed to upload ${file.name}:`, err);
      }
    }
    setUploading(false);
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    multiple: true,
  });

  const deleteDocument = async (filename) => {
    try {
      await axios.delete(`${API_URL}/documents/${encodeURIComponent(filename)}`);
      fetchDocuments();
    } catch (err) {
      console.error('Failed to delete document:', err);
    }
  };

  const sendMessage = async () => {
    if (!input.trim() || loading) return;

    const userMessage = { role: 'user', content: input };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setLoading(true);
    setStreaming(true);

    try {
      const response = await fetch(`${API_URL}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMessage.content,
          conversation_id: conversationId,
        }),
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let assistantContent = '';
      let sources = [];
      let buffer = '';

      setMessages(prev => [...prev, { role: 'assistant', content: '', sources: [] }]);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.trim() || !line.startsWith('data: ')) continue;
          const data = line.slice(6);

          if (data === '[DONE]') break;

          try {
            const parsed = JSON.parse(data);
            if (parsed.type === 'sources') {
              sources = parsed.content;
              setMessages(prev => {
                const updated = [...prev];
                updated[updated.length - 1] = {
                  ...updated[updated.length - 1],
                  sources: parsed.content,
                };
                return updated;
              });
            } else if (parsed.type === 'token') {
              assistantContent += parsed.content;
              setMessages(prev => {
                const updated = [...prev];
                updated[updated.length - 1] = {
                  ...updated[updated.length - 1],
                  content: assistantContent,
                };
                return updated;
              });
            } else if (parsed.type === 'done') {
              if (parsed.conversation_id) {
                setConversationId(parsed.conversation_id);
              }
            }
          } catch (e) {
            // skip parse errors for partial data
          }
        }
      }
    } catch (err) {
      console.error('Chat error:', err);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Sorry, something went wrong. Please try again.',
        sources: []
      }]);
    } finally {
      setLoading(false);
      setStreaming(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="app">
      {/* Sidebar */}
      <div className={`sidebar ${showSidebar ? 'open' : 'closed'}`}>
        <div className="sidebar-header">
          <h2>📄 Documents</h2>
          <button className="toggle-btn" onClick={() => setShowSidebar(!showSidebar)}>
            {showSidebar ? '◀' : '▶'}
          </button>
        </div>

        {/* Upload Zone */}
        <div {...getRootProps()} className={`dropzone ${isDragActive ? 'active' : ''}`}>
          <input {...getInputProps()} />
          {uploading ? (
            <p>⏳ Uploading...</p>
          ) : isDragActive ? (
            <p>📥 Drop PDFs here...</p>
          ) : (
            <p>📤 Drag & drop PDFs or click</p>
          )}
        </div>

        {/* Document List */}
        <div className="doc-list">
          {documents.length === 0 ? (
            <p className="empty-docs">No documents uploaded yet</p>
          ) : (
            documents.map((doc, i) => (
              <div key={i} className="doc-item">
                <span className="doc-icon">📄</span>
                <span className="doc-name" title={doc.filename}>{doc.filename}</span>
                <button
                  className="delete-doc"
                  onClick={() => deleteDocument(doc.filename)}
                  title="Delete document"
                >
                  🗑️
                </button>
              </div>
            ))
          )}
        </div>

        <div className="sidebar-footer">
          <p className="sidebar-info">
            {documents.length} document{documents.length !== 1 ? 's' : ''} loaded
          </p>
        </div>
      </div>

      {/* Toggle sidebar button when closed */}
      {!showSidebar && (
        <button className="toggle-btn floating" onClick={() => setShowSidebar(true)}>
          ▶
        </button>
      )}

      {/* Main Chat Area */}
      <div className="chat-area">
        <header className="chat-header">
          <h1>🤖 RAG Chatbot</h1>
          <span className="header-subtitle">Ask questions about your documents</span>
        </header>

        <div className="messages">
          {messages.length === 0 && (
            <div className="welcome">
              <div className="welcome-icon">📚</div>
              <h2>Welcome to RAG Chatbot</h2>
              <p>Upload PDF documents and ask questions about their content.</p>
              <p>I'll answer with citations back to the source documents.</p>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`message ${msg.role}`}>
              <div className="message-avatar">
                {msg.role === 'user' ? '👤' : '🤖'}
              </div>
              <div className="message-content">
                {msg.role === 'assistant' ? (
                  <>
                    <ReactMarkdown>{msg.content || '⏳ Thinking...'}</ReactMarkdown>
                    {msg.sources && msg.sources.length > 0 && (
                      <div className="sources">
                        <h4>📎 Sources:</h4>
                        {msg.sources.map((src, j) => (
                          <div key={j} className="source-item">
                            <span className="source-badge">
                              {src.filename} {src.page !== 'N/A' ? `(p.${src.page})` : ''}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                ) : (
                  <p>{msg.content}</p>
                )}
              </div>
            </div>
          ))}

          {loading && streaming && !messages[messages.length - 1]?.content && (
            <div className="message assistant">
              <div className="message-avatar">🤖</div>
              <div className="message-content">
                <div className="typing-indicator">
                  <span></span><span></span><span></span>
                </div>
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        {/* Input Area */}
        <div className="input-area">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question about your documents..."
            rows={2}
            disabled={loading}
          />
          <button
            className="send-btn"
            onClick={sendMessage}
            disabled={!input.trim() || loading}
          >
            {loading ? '⏳' : '➤'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default App;
