import React, { useState, useEffect, useCallback } from 'react';
import { apiGet, apiPost, apiDelete, apiUpload } from '../api/client';
import { useAuth } from '../context/AuthContext';

const SAMPLE_MCQ_TEXT = `Q: What is the cancellation policy?
A) Free cancellation up to 24 hours in advance
B) 50% fee within 24 hours
C) No refunds under any circumstance
Answer: A
Explanation: Appointments can be rescheduled or cancelled without penalty at least 24 hours prior.

Q: What are the front desk operating hours?
A) 9:00 AM to 5:00 PM Monday through Friday
B) 8:00 AM to 6:00 PM Monday through Saturday
C) 24 hours open every day
Answer: B
Explanation: The reception desk is staffed Monday through Saturday from 8 AM to 6 PM EST.`;

export default function KnowledgeBaseModal({ isOpen, onClose, personas = [], currentPersona = 'concierge' }) {
  const { isAuthenticated } = useAuth();
  const [activeTab, setActiveTab] = useState('documents'); // 'documents' | 'upload' | 'mcq' | 'search'

  // Documents list state
  const [documents, setDocuments] = useState([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [docActionError, setDocActionError] = useState(null);

  // File upload state
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploadTitle, setUploadTitle] = useState('');
  const [targetPersona, setTargetPersona] = useState(currentPersona);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadSuccess, setUploadSuccess] = useState(null);

  // Raw text / MCQ state
  const [mcqTitle, setMcqTitle] = useState('');
  const [mcqContent, setMcqContent] = useState('');
  const [mcqPersona, setMcqPersona] = useState(currentPersona);
  const [isIngestingMcq, setIsIngestingMcq] = useState(false);
  const [mcqSuccess, setMcqSuccess] = useState(null);

  // Semantic query test state
  const [queryText, setQueryText] = useState('');
  const [queryPersona, setQueryPersona] = useState(currentPersona);
  const [isSearching, setIsSearching] = useState(false);
  const [searchResults, setSearchResults] = useState(null);

  // Fetch documents for the active user
  const fetchDocuments = useCallback(async () => {
    setDocsLoading(true);
    setDocActionError(null);
    try {
      const res = await apiGet('/api/knowledge/documents');
      if (res.ok) {
        const data = await res.json();
        setDocuments(data || []);
      } else {
        setDocActionError('Failed to load knowledge documents.');
      }
    } catch (e) {
      setDocActionError(e.message || 'Error fetching documents.');
    } finally {
      setDocsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      fetchDocuments();
      setTargetPersona(currentPersona);
      setMcqPersona(currentPersona);
      setQueryPersona(currentPersona);
    }
  }, [isOpen, currentPersona, fetchDocuments]);

  if (!isOpen) return null;

  // File Upload Handler
  const handleFileUpload = async (e) => {
    e.preventDefault();
    if (!selectedFile) return;

    setIsUploading(true);
    setUploadSuccess(null);
    setDocActionError(null);

    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('persona_id', targetPersona);
    if (uploadTitle.trim()) {
      formData.append('title', uploadTitle.trim());
    }

    try {
      const res = await apiUpload('/api/knowledge/upload', formData);
      const data = await res.json();
      if (res.ok) {
        setUploadSuccess(`Successfully indexed "${data.filename}" (${data.result.chunks_indexed} chunks) into ChromaDB!`);
        setSelectedFile(null);
        setUploadTitle('');
        fetchDocuments();
      } else {
        setDocActionError(data.detail || 'Upload failed.');
      }
    } catch (err) {
      setDocActionError(err.message || 'Error during file upload.');
    } finally {
      setIsUploading(false);
    }
  };

  // MCQ / Raw Text Ingest Handler
  const handleMcqSubmit = async (e) => {
    e.preventDefault();
    if (!mcqContent.trim() || !mcqTitle.trim()) return;

    setIsIngestingMcq(true);
    setMcqSuccess(null);
    setDocActionError(null);

    try {
      const res = await apiPost('/api/knowledge/mcq', {
        title: mcqTitle.trim(),
        mcqs: mcqContent.trim(),
        persona_id: mcqPersona,
      });
      const data = await res.json();
      if (res.ok) {
        setMcqSuccess(`Successfully parsed and indexed ${data.result.chunks_indexed} MCQ chunks!`);
        setMcqContent('');
        setMcqTitle('');
        fetchDocuments();
      } else {
        setDocActionError(data.detail || 'MCQ ingestion failed.');
      }
    } catch (err) {
      setDocActionError(err.message || 'Error ingesting MCQs.');
    } finally {
      setIsIngestingMcq(false);
    }
  };

  // Semantic Test Search Handler
  const handleTestSearch = async (e) => {
    e.preventDefault();
    if (!queryText.trim()) return;

    setIsSearching(true);
    setSearchResults(null);
    try {
      const res = await apiPost('/api/knowledge/query', {
        query: queryText.trim(),
        persona_id: queryPersona,
        top_k: 4,
        threshold: 0.1,
      });
      if (res.ok) {
        const data = await res.json();
        setSearchResults(data);
      } else {
        const err = await res.json();
        setDocActionError(err.detail || 'Query failed.');
      }
    } catch (err) {
      setDocActionError(err.message || 'Error executing search.');
    } finally {
      setIsSearching(false);
    }
  };

  // Delete Document
  const handleDeleteDoc = async (docId, title) => {
    if (!window.confirm(`Delete "${title}" and all its vector chunks from ChromaDB?`)) return;

    try {
      const res = await apiDelete(`/api/knowledge/documents/${docId}`);
      if (res.ok) {
        setDocuments((prev) => prev.filter((d) => d.document_id !== docId));
      } else {
        const err = await res.json();
        alert('Could not delete document: ' + (err.detail || 'Error'));
      }
    } catch (e) {
      alert('Delete failed: ' + e.message);
    }
  };

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <div className="rag-modal-panel card-glass" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="drawer-header">
          <div className="history-header-title">
            <div className="rag-title-row">
              <span className="rag-icon">📚</span>
              <h2>Knowledge Base & RAG</h2>
            </div>
            <span className="badge-user-scope">ChromaDB + Gemini Embeddings</span>
          </div>
          <button className="btn-icon" onClick={onClose} title="Close">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="20" height="20">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>

        {/* Tab Switcher */}
        <div className="rag-tab-bar">
          <button
            type="button"
            className={`rag-tab-btn ${activeTab === 'documents' ? 'active' : ''}`}
            onClick={() => setActiveTab('documents')}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
            </svg>
            <span>Indexed Documents ({documents.length})</span>
          </button>

          <button
            type="button"
            className={`rag-tab-btn ${activeTab === 'upload' ? 'active' : ''}`}
            onClick={() => setActiveTab('upload')}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
              <polyline points="17 8 12 3 7 8"></polyline>
              <line x1="12" y1="3" x2="12" y2="15"></line>
            </svg>
            <span>Upload Document</span>
          </button>

          <button
            type="button"
            className={`rag-tab-btn ${activeTab === 'mcq' ? 'active' : ''}`}
            onClick={() => setActiveTab('mcq')}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
              <polyline points="9 11 12 14 22 4"></polyline>
              <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path>
            </svg>
            <span>MCQ & Q/A Editor</span>
          </button>

          <button
            type="button"
            className={`rag-tab-btn ${activeTab === 'search' ? 'active' : ''}`}
            onClick={() => setActiveTab('search')}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
            </svg>
            <span>Semantic Test Search</span>
          </button>
        </div>

        {/* Global Error Banner */}
        {docActionError && (
          <div className="rag-alert rag-alert-error">
            <span>{docActionError}</span>
            <button type="button" onClick={() => setDocActionError(null)}>✕</button>
          </div>
        )}

        {/* Tab 1: Documents List */}
        {activeTab === 'documents' && (
          <div className="rag-tab-content">
            <div className="rag-section-header">
              <div>
                <h3>Indexed Knowledge Documents</h3>
                <p>Documents partitioned in ChromaDB for fast sub-50ms voice agent retrieval.</p>
              </div>
              <button
                type="button"
                className="btn-text-action"
                onClick={fetchDocuments}
                disabled={docsLoading}
              >
                {docsLoading ? 'Refreshing...' : '↻ Refresh'}
              </button>
            </div>

            {docsLoading ? (
              <div className="history-empty-state">Loading knowledge records...</div>
            ) : documents.length === 0 ? (
              <div className="rag-empty-box">
                <span className="rag-empty-icon">📂</span>
                <h4>No Knowledge Documents Yet</h4>
                <p>Upload a clinic PDF, school handbook, or MCQ FAQ sheet so the voice copilot can cite answers during live calls.</p>
                <button
                  type="button"
                  className="btn-header-primary"
                  onClick={() => setActiveTab('upload')}
                >
                  Upload First Document
                </button>
              </div>
            ) : (
              <div className="rag-doc-grid">
                {documents.map((doc) => (
                  <div key={doc.document_id} className="rag-doc-card">
                    <div className="rag-doc-card-header">
                      <div className="rag-doc-badge-group">
                        <span className={`rag-type-pill pill-${doc.doc_type || 'text'}`}>
                          {(doc.doc_type || 'doc').toUpperCase()}
                        </span>
                        {doc.is_mcq && <span className="rag-type-pill pill-mcq">MCQ</span>}
                        <span className="rag-persona-tag">@{doc.persona_id || 'all'}</span>
                      </div>
                      <button
                        type="button"
                        className="btn-doc-delete"
                        onClick={() => handleDeleteDoc(doc.document_id, doc.title)}
                        title="Delete from Vector Store"
                      >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                          <polyline points="3 6 5 6 21 6"></polyline>
                          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                        </svg>
                      </button>
                    </div>

                    <h4 className="rag-doc-title" title={doc.title}>{doc.title}</h4>

                    <div className="rag-doc-stats">
                      <span><strong>{doc.chunk_count}</strong> vector chunks</span>
                      <span>ID: <code>{doc.document_id.slice(0, 10)}...</code></span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Tab 2: Upload Document */}
        {activeTab === 'upload' && (
          <div className="rag-tab-content">
            <form onSubmit={handleFileUpload} className="rag-form-layout">
              <div className="rag-section-header">
                <div>
                  <h3>Upload Document (.pdf, .md, .txt)</h3>
                  <p>Pure-Python stream parsing with page tracking and heading-aware chunking.</p>
                </div>
              </div>

              {uploadSuccess && (
                <div className="rag-alert rag-alert-success">
                  {uploadSuccess}
                </div>
              )}

              <div className="form-group">
                <label className="form-label">Select File (.pdf, .md, .txt)</label>
                <div className="rag-dropzone">
                  <input
                    type="file"
                    id="rag-file-input"
                    accept=".pdf,.md,.txt"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) {
                        setSelectedFile(file);
                        if (!uploadTitle) {
                          setUploadTitle(file.name.replace(/\.[^/.]+$/, ''));
                        }
                      }
                    }}
                  />
                  <label htmlFor="rag-file-input" className="dropzone-label">
                    <span className="dropzone-icon">📄</span>
                    {selectedFile ? (
                      <strong>Selected: {selectedFile.name} ({(selectedFile.size / 1024).toFixed(1)} KB)</strong>
                    ) : (
                      <span>Click to choose PDF, Markdown, or Text file</span>
                    )}
                  </label>
                </div>
              </div>

              <div className="rag-form-row">
                <div className="form-group flex-1">
                  <label className="form-label">Document Display Title (Optional)</label>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="e.g. Clinic Appointment Guidelines"
                    value={uploadTitle}
                    onChange={(e) => setUploadTitle(e.target.value)}
                  />
                </div>

                <div className="form-group flex-1">
                  <label className="form-label">Target Persona Scope</label>
                  <select
                    className="form-select"
                    value={targetPersona}
                    onChange={(e) => setTargetPersona(e.target.value)}
                  >
                    {personas.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.icon || '🤖'} {p.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <button
                type="submit"
                className="btn-header-primary btn-submit-rag"
                disabled={!selectedFile || isUploading}
              >
                {isUploading ? 'Chunking & Indexing Embeddings...' : 'Index Document into Vector Store'}
              </button>
            </form>
          </div>
        )}

        {/* Tab 3: MCQ & Q/A Editor */}
        {activeTab === 'mcq' && (
          <div className="rag-tab-content">
            <form onSubmit={handleMcqSubmit} className="rag-form-layout">
              <div className="rag-section-header">
                <div>
                  <h3>Atomic MCQ & FAQ Ingestion</h3>
                  <p>Guarantees Question, Options, and Answers stay bound together as atomic chunks.</p>
                </div>
                <button
                  type="button"
                  className="btn-chip"
                  onClick={() => {
                    setMcqTitle('Clinic Policy MCQs');
                    setMcqContent(SAMPLE_MCQ_TEXT);
                  }}
                >
                  Insert Sample MCQ Template
                </button>
              </div>

              {mcqSuccess && (
                <div className="rag-alert rag-alert-success">
                  {mcqSuccess}
                </div>
              )}

              <div className="rag-form-row">
                <div className="form-group flex-1">
                  <label className="form-label">MCQ Collection Title</label>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="e.g. Front-Desk FAQ MCQs"
                    value={mcqTitle}
                    onChange={(e) => setMcqTitle(e.target.value)}
                    required
                  />
                </div>

                <div className="form-group flex-1">
                  <label className="form-label">Target Persona</label>
                  <select
                    className="form-select"
                    value={mcqPersona}
                    onChange={(e) => setMcqPersona(e.target.value)}
                  >
                    {personas.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.icon || '🤖'} {p.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Multiple Choice Questions (Plain Text or Standard Format)</label>
                <textarea
                  className="form-textarea rag-mcq-textarea"
                  rows={9}
                  placeholder={`Q: What is the cancellation policy?\nA) Free up to 24 hours\nB) 50% charge\nAnswer: A\nExplanation: ...`}
                  value={mcqContent}
                  onChange={(e) => setMcqContent(e.target.value)}
                  required
                />
              </div>

              <button
                type="submit"
                className="btn-header-primary btn-submit-rag"
                disabled={!mcqContent.trim() || !mcqTitle.trim() || isIngestingMcq}
              >
                {isIngestingMcq ? 'Parsing & Embedding Atomic MCQs...' : 'Ingest Atomic MCQ Units'}
              </button>
            </form>
          </div>
        )}

        {/* Tab 4: Semantic Test Search */}
        {activeTab === 'search' && (
          <div className="rag-tab-content">
            <div className="rag-section-header">
              <div>
                <h3>Semantic Test Search</h3>
                <p>Simulate what the Voice AI agent retrieves when a caller asks a question.</p>
              </div>
            </div>

            <form onSubmit={handleTestSearch} className="rag-search-bar-row">
              <input
                type="text"
                className="form-input flex-1"
                placeholder="Ask any question (e.g., 'What is the cancellation policy?')"
                value={queryText}
                onChange={(e) => setQueryText(e.target.value)}
              />
              <select
                className="form-select rag-search-persona-select"
                value={queryPersona}
                onChange={(e) => setQueryPersona(e.target.value)}
              >
                {personas.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              <button
                type="submit"
                className="btn-header-primary"
                disabled={!queryText.trim() || isSearching}
              >
                {isSearching ? 'Searching...' : 'Search'}
              </button>
            </form>

            {searchResults && (
              <div className="rag-results-container">
                <div className="rag-results-meta">
                  <span>Found <strong>{searchResults.count}</strong> matching chunks</span>
                  <span>Retrieval Latency: <strong>{searchResults.latency_ms} ms</strong></span>
                </div>

                {searchResults.matches.length === 0 ? (
                  <div className="rag-empty-box">
                    <span>🔍</span>
                    <p>No document chunks matched this query above the similarity threshold.</p>
                  </div>
                ) : (
                  <div className="rag-results-list">
                    {searchResults.matches.map((match, idx) => (
                      <div key={match.id || idx} className="rag-match-card">
                        <div className="rag-match-header">
                          <div className="rag-match-source">
                            <span className="rag-source-num">#{idx + 1}</span>
                            <strong>{match.metadata?.document_title || 'Document'}</strong>
                            {match.metadata?.page_number && (
                              <span className="rag-page-tag">Page {match.metadata.page_number}</span>
                            )}
                            {match.metadata?.is_mcq && (
                              <span className="rag-type-pill pill-mcq">MCQ</span>
                            )}
                          </div>
                          <span className="rag-similarity-badge">
                            {(match.similarity * 100).toFixed(1)}% Match
                          </span>
                        </div>
                        <div className="rag-match-text">
                          {match.text}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
