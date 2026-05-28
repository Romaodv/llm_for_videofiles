import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Activity, AlertTriangle, CheckCircle2, Cpu, Database, FileVideo, FolderOpen, Play, RefreshCcw, Save, Search, Send, Settings, SkipForward, Trash2, X } from "lucide-react";

const API_BASE =
  window.__LLM_FORFILES_API_BASE__ ??
  (window.location.protocol === "http:" || window.location.protocol === "https:" ? window.location.origin : undefined) ??
  import.meta.env.VITE_API_BASE_URL ??
  "http://127.0.0.1:8000";

type DocumentItem = {
  id: number;
  source_path: string;
  web_video_path: string | null;
  file_name: string;
  duration_seconds: number;
  indexed_at: string;
  saved_at: string | null;
  category: string;
  notes: string;
  embedding_provider: string;
  embedding_model: string;
  chunk_count: number;
};

type TranscriptCue = {
  cue_index: number;
  start_seconds: number;
  end_seconds: number;
  text: string;
};

type Topic = {
  id: number;
  start_seconds: number;
  end_seconds: number;
  title: string;
  summary: string;
};

type SourceHit = {
  chunk_id: number;
  document_id: number;
  file_name: string;
  source_path: string;
  start_seconds: number;
  end_seconds: number;
  text: string;
  score: number;
};

type ChatMessage = {
  role: "user" | "assistant";
  text: string;
  sources?: SourceHit[];
};

type FileEntry = {
  name: string;
  path: string;
  is_dir: boolean;
  size: number | null;
};

type JobLog = {
  time: string;
  phase: string;
  percent: number;
  message: string;
  detail: string;
};

type JobState = {
  id: string;
  kind: string;
  status: "queued" | "running" | "completed" | "failed";
  phase: string;
  percent: number;
  message: string;
  detail: string;
  result: { document_id?: number; status?: string; chunk_count?: number } | null;
  error: string | null;
  logs: JobLog[];
  created_at: string;
  updated_at: string;
};

type PresentationSummary = {
  markdown: string;
  provider: string;
  model: string;
  generated_at: string;
};

type SecretStatus = {
  provider: string;
  configured: boolean;
  masked: string | null;
  storage: string;
};

type WhisperModelName = "tiny" | "base" | "small" | "medium" | "large-v3";
type TranscriptionProvider = "local" | "groq";
type LlmProvider = "deepseek" | "groq";
type GroqLlmModel = "meta-llama/llama-4-scout-17b-16e-instruct" | "groq/compound-mini";
type LongSummaryMode = "deepseek_full" | "groq_full" | "groq_chunked";

export function App() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const messagesRef = useRef<HTMLDivElement | null>(null);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [selected, setSelected] = useState<DocumentItem | null>(null);
  const [path, setPath] = useState("");
  const [folder, setFolder] = useState("");
  const [entries, setEntries] = useState<FileEntry[]>([]);
  const [parent, setParent] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<TranscriptCue[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [presentationSummary, setPresentationSummary] = useState("");
  const [topicTab, setTopicTab] = useState<"topics" | "summary">("topics");
  const [question, setQuestion] = useState("");
  const [chat, setChat] = useState<ChatMessage[]>([]);
  const [deepseekApiKey, setDeepseekApiKey] = useState("");
  const [groqApiKey, setGroqApiKey] = useState("");
  const [srtSearch, setSrtSearch] = useState("");
  const [deepseekSecretStatus, setDeepseekSecretStatus] = useState<SecretStatus | null>(null);
  const [groqSecretStatus, setGroqSecretStatus] = useState<SecretStatus | null>(null);
  const [llmProvider, setLlmProviderState] = useState<LlmProvider>(() => {
    return window.localStorage.getItem("llm_forfiles_llm_provider") === "groq" ? "groq" : "deepseek";
  });
  const [groqLlmModel, setGroqLlmModelState] = useState<GroqLlmModel>(() => {
    return window.localStorage.getItem("llm_forfiles_groq_llm_model") === "groq/compound-mini"
      ? "groq/compound-mini"
      : "meta-llama/llama-4-scout-17b-16e-instruct";
  });
  const [longSummaryMode, setLongSummaryModeState] = useState<LongSummaryMode>(() => {
    const value = window.localStorage.getItem("llm_forfiles_long_summary_mode");
    return value === "groq_full" || value === "groq_chunked" ? value : "deepseek_full";
  });
  const [configOpen, setConfigOpen] = useState(false);
  const [transcriptionOpen, setTranscriptionOpen] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [currentTime, setCurrentTime] = useState(0);
  const [reindex, setReindex] = useState(false);
  const [transcriptionProvider, setTranscriptionProvider] = useState<TranscriptionProvider>("local");
  const [whisperCpuThreads, setWhisperCpuThreads] = useState(2);
  const [whisperModel, setWhisperModel] = useState<WhisperModelName>("base");
  const [category, setCategory] = useState("Sem categoria");
  const [notes, setNotes] = useState("");
  const [job, setJob] = useState<JobState | null>(null);
  const [videoWarning, setVideoWarning] = useState("");

  useEffect(() => {
    loadDocuments();
    loadFolder(window.__LLM_FORFILES_HOME_DIR__);
    loadSecretStatus().catch(showError);
  }, []);

  useEffect(() => {
    if (!selected) return;
    setCategory(selected.category || "Sem categoria");
    setNotes(selected.notes || "");
    setVideoWarning("");
    setPresentationSummary("");
    setTopicTab("topics");
    Promise.all([loadTranscript(selected.id), loadTopics(selected.id), loadPresentationSummary(selected.id)]).catch(showError);
  }, [selected]);


  useEffect(() => {
    if (!messagesRef.current) return;
    messagesRef.current.scrollTo({ top: messagesRef.current.scrollHeight, behavior: "smooth" });
  }, [chat, busy]);

  useEffect(() => {
    if (!job || (job.status !== "queued" && job.status !== "running")) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await api<JobState>(`/jobs/${job.id}`);
        setJob(next);
        if (next.status === "completed") {
          const docs = await api<DocumentItem[]>("/documents");
          setDocuments(docs);
          const documentId = next.result?.document_id;
          setSelected(docs.find((doc) => doc.id === documentId) ?? docs[0] ?? null);
          setBusy("");
        }
        if (next.status === "failed") {
          setError(next.error ?? "Falha no processamento");
          setBusy("");
        }
      } catch (err) {
        showError(err);
        setBusy("");
      }
    }, 900);
    return () => window.clearInterval(timer);
  }, [job]);

  const activeCue = useMemo(
    () => transcript.find((cue) => cue.start_seconds <= currentTime && cue.end_seconds >= currentTime),
    [currentTime, transcript],
  );

  const groupedDocuments = useMemo(() => {
    return documents.reduce<Record<string, DocumentItem[]>>((groups, doc) => {
      const key = doc.category || "Sem categoria";
      groups[key] = [...(groups[key] ?? []), doc];
      return groups;
    }, {});
  }, [documents]);

  const filteredTranscript = useMemo(() => {
    const query = srtSearch.trim().toLowerCase();
    if (!query) return transcript;
    return transcript.filter((cue) => {
      return cue.text.toLowerCase().includes(query) || formatTime(cue.start_seconds).includes(query);
    });
  }, [srtSearch, transcript]);

  async function api<T>(url: string, options?: RequestInit): Promise<T> {
    const response = await fetch(`${API_BASE}${url}`, {
      headers: { "Content-Type": "application/json", ...(options?.headers ?? {}) },
      ...options,
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(payload.detail ?? response.statusText);
    }
    return response.json();
  }

  function showError(value: unknown) {
    setError(value instanceof Error ? value.message : String(value));
  }

  function setLlmProvider(value: LlmProvider) {
    setLlmProviderState(value);
    window.localStorage.setItem("llm_forfiles_llm_provider", value);
  }

  function setGroqLlmModel(value: GroqLlmModel) {
    setGroqLlmModelState(value);
    window.localStorage.setItem("llm_forfiles_groq_llm_model", value);
  }

  function setLongSummaryMode(value: LongSummaryMode) {
    setLongSummaryModeState(value);
    window.localStorage.setItem("llm_forfiles_long_summary_mode", value);
  }

  function longSummaryQuery() {
    const provider = longSummaryMode === "deepseek_full" ? "deepseek" : "groq";
    const strategy = longSummaryMode === "groq_chunked" ? "chunked" : "full";
    return new URLSearchParams({
      llm_provider: provider,
      groq_llm_model: groqLlmModel,
      summary_strategy: strategy,
    });
  }

  async function loadDocuments() {
    setDocuments(await api<DocumentItem[]>("/documents"));
  }

  async function loadFolder(nextPath?: string) {
    try {
      const suffix = nextPath ? `?path=${encodeURIComponent(nextPath)}` : "";
      const result = await api<{ path: string; parent: string | null; entries: FileEntry[] }>(`/files/list${suffix}`);
      setFolder(result.path);
      setParent(result.parent);
      setEntries(result.entries);
    } catch (err) {
      showError(err);
      setFolder(nextPath ?? "");
      setParent(null);
      setEntries([]);
    }
  }

  async function pickVideo() {
    if (!window.llmForfilesDesktop?.pickVideo) return;
    const selectedPath = await window.llmForfilesDesktop.pickVideo();
    if (selectedPath) {
      setPath(selectedPath);
      const lastSlash = Math.max(selectedPath.lastIndexOf("/"), selectedPath.lastIndexOf("\\"));
      if (lastSlash > 0) {
        void loadFolder(selectedPath.slice(0, lastSlash));
      }
    }
  }

  async function pickFolder() {
    if (!window.llmForfilesDesktop?.pickFolder) return;
    const selectedPath = await window.llmForfilesDesktop.pickFolder();
    if (selectedPath) {
      await loadFolder(selectedPath);
    }
  }

  async function loadTranscript(documentId: number) {
    setTranscript(await api<TranscriptCue[]>(`/documents/${documentId}/transcript`));
  }

  async function loadTopics(documentId: number) {
    setTopics(await api<Topic[]>(`/documents/${documentId}/topics`));
  }

  async function loadPresentationSummary(documentId: number) {
    const result = await api<PresentationSummary>(`/documents/${documentId}/summary`);
    setPresentationSummary(result.markdown || "");
  }

  async function loadSecretStatus() {
    const [deepseek, groq] = await Promise.all([
      api<SecretStatus>("/settings/secrets/deepseek"),
      api<SecretStatus>("/settings/secrets/groq"),
    ]);
    setDeepseekSecretStatus(deepseek);
    setGroqSecretStatus(groq);
  }

  async function saveApiKey(provider: "deepseek" | "groq", value: string) {
    if (!value.trim()) return;
    setBusy(`secret-${provider}`);
    setError("");
    try {
      const status = await api<SecretStatus>(`/settings/secrets/${provider}`, {
        method: "POST",
        body: JSON.stringify({ api_key: value.trim() }),
      });
      if (provider === "deepseek") {
        setDeepseekSecretStatus(status);
        setDeepseekApiKey("");
      } else {
        setGroqSecretStatus(status);
        setGroqApiKey("");
      }
    } catch (err) {
      showError(err);
    } finally {
      setBusy("");
    }
  }

  async function deleteApiKey(provider: "deepseek" | "groq") {
    setBusy(`secret-${provider}`);
    setError("");
    try {
      const status = await api<SecretStatus>(`/settings/secrets/${provider}`, { method: "DELETE" });
      if (provider === "deepseek") {
        setDeepseekSecretStatus(status);
        setDeepseekApiKey("");
      } else {
        setGroqSecretStatus(status);
        setGroqApiKey("");
      }
    } catch (err) {
      showError(err);
    } finally {
      setBusy("");
    }
  }

  async function summarizeTopics() {
    if (!selected) return;
    setBusy("topics");
    setError("");
    try {
      const query = longSummaryQuery();
      setTopics(await api<Topic[]>(`/documents/${selected.id}/topics/summarize?${query.toString()}`, { method: "POST" }));
      setPresentationSummary("");
      setTopicTab("topics");
    } catch (err) {
      showError(err);
    } finally {
      setBusy("");
    }
  }

  async function summarizePresentation() {
    if (!selected) return;
    setBusy("summary");
    setError("");
    try {
      const query = longSummaryQuery();
      const result = await api<PresentationSummary & { topics: Topic[] }>(`/documents/${selected.id}/summary?${query.toString()}`, { method: "POST" });
      setTopics(result.topics);
      setPresentationSummary(result.markdown);
      setTopicTab("summary");
    } catch (err) {
      showError(err);
    } finally {
      setBusy("");
    }
  }

  async function indexVideo() {
    if (!path.trim()) return;
    setBusy("index");
    setError("");
    setTranscriptionOpen(false);
    try {
      const result = await api<{ job_id: string }>("/videos/index/jobs", {
        method: "POST",
        body: JSON.stringify({
          path: path.trim(),
          reindex,
          transcribe: true,
          category,
          transcription_provider: transcriptionProvider,
          whisper_cpu_threads: whisperCpuThreads,
          whisper_model: whisperModel,
        }),
      });
      setJob({
        id: result.job_id,
        kind: "video_index",
        status: "queued",
        phase: "queued",
        percent: 0,
        message: "Job enviado",
        detail: "Aguardando backend iniciar",
        result: null,
        error: null,
        logs: [],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
    } catch (err) {
      showError(err);
      setBusy("");
    }
  }

  async function saveDocument() {
    if (!selected) return;
    setBusy("save");
    setError("");
    try {
      const updated = await api<DocumentItem>(`/documents/${selected.id}/save`, {
        method: "PUT",
        body: JSON.stringify({ category, notes }),
      });
      const docs = await api<DocumentItem[]>("/documents");
      setDocuments(docs);
      setSelected(updated);
    } catch (err) {
      showError(err);
    } finally {
      setBusy("");
    }
  }

  async function deleteIndexedDocument(doc: DocumentItem) {
    const confirmed = window.confirm(`Excluir a indexacao de "${doc.file_name}"? O video original nao sera apagado.`);
    if (!confirmed) return;
    setBusy("delete-document");
    setError("");
    try {
      await api<{ deleted: boolean }>(`/documents/${doc.id}`, { method: "DELETE" });
      const docs = await api<DocumentItem[]>("/documents");
      setDocuments(docs);
      if (selected?.id === doc.id) {
        setSelected(docs[0] ?? null);
        setTranscript([]);
        setTopics([]);
        setPresentationSummary("");
        setChat([]);
      }
    } catch (err) {
      showError(err);
    } finally {
      setBusy("");
    }
  }

  async function convertMedia() {
    if (!selected) return;
    setBusy("media");
    setError("");
    try {
      const result = await api<{ job_id: string }>(`/documents/${selected.id}/media/jobs`, { method: "POST" });
      setJob({
        id: result.job_id,
        kind: "web_media",
        status: "queued",
        phase: "queued",
        percent: 0,
        message: "Conversao enviada",
        detail: "Gerando MP4 H.264/AAC compativel com o navegador",
        result: null,
        error: null,
        logs: [],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
    } catch (err) {
      showError(err);
      setBusy("");
    }
  }

  async function ask(event: FormEvent) {
    event.preventDefault();
    if (!question.trim()) return;
    const userQuestion = question.trim();
    setQuestion("");
    setChat((messages) => [...messages, { role: "user", text: userQuestion }]);
    setBusy("ask");
    setError("");
    try {
      const history = chat.slice(-8).map((message) => ({ role: message.role, text: message.text }));
      const result = await api<{ answer: string; sources: SourceHit[] }>("/search/ask", {
        method: "POST",
        body: JSON.stringify({
          question: userQuestion,
          document_id: selected?.id,
          top_k: 8,
          mode: "cloud",
          llm_provider: llmProvider,
          groq_llm_model: groqLlmModel,
          history,
          cloud_api_key: null,
        }),
      });
      setChat((messages) => [...messages, { role: "assistant", text: result.answer, sources: result.sources }]);
    } catch (err) {
      showError(err);
    } finally {
      setBusy("");
    }
  }

  function jumpTo(seconds: number) {
    if (!videoRef.current) return;
    videoRef.current.currentTime = seconds;
    videoRef.current.play().catch(() => undefined);
  }

  const mediaUrl = selected ? `${API_BASE}/documents/${selected.id}/media` : "";
  const videoKey = selected ? `${selected.id}-${selected.web_video_path ?? "original"}` : "empty";

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <button className="config-button" type="button" title="Configurar APIs" onClick={() => setConfigOpen(true)}>
            <Settings size={16} />
          </button>
          <FileVideo size={20} />
          <span>Video RAG</span>
        </div>
        <div className="system-badge">
          <span className="pulse" />
          <span>Local SQLite · {transcriptionProvider === "groq" ? "Groq Whisper v3 turbo" : `Whisper ${whisperModel}`} · RAG</span>
        </div>

        <section className="panel">
          <div className="panel-title">
            <FolderOpen size={16} />
            <span>Arquivos</span>
          </div>
          <div className="path-row">
            <input value={path} onChange={(event) => setPath(event.target.value)} placeholder="/caminho/video.mp4" />
            <button title="Selecionar video" onClick={() => void pickVideo()} type="button">
              <FolderOpen size={16} />
            </button>
            <button title="Transcrever e indexar" onClick={() => path.trim() && setTranscriptionOpen(true)} disabled={busy === "index" || !path.trim()}>
              {busy === "index" ? <RefreshCcw className="spin" size={16} /> : <Play size={16} />}
            </button>
          </div>
          <input value={category} onChange={(event) => setCategory(event.target.value)} placeholder="Categoria" />
          <div className="folder-bar">
            <button onClick={() => parent && loadFolder(parent)} disabled={!parent}>
              ..
            </button>
            <button onClick={() => void pickFolder()} type="button" title="Abrir pasta">
              <FolderOpen size={14} />
            </button>
            <span title={folder}>{folder}</span>
          </div>
          <div className="file-list">
            {entries.map((entry) => (
              <button
                key={entry.path}
                className={entry.is_dir ? "entry dir" : "entry"}
                onClick={() => (entry.is_dir ? loadFolder(entry.path) : setPath(entry.path))}
              >
                <span>{entry.is_dir ? "[]" : ">"}</span>
                <strong>{entry.name}</strong>
              </button>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="panel-title">
            <Search size={16} />
            <span>Indexados</span>
          </div>
          <div className="doc-list">
            {Object.entries(groupedDocuments).map(([group, docs]) => (
              <div className="doc-group" key={group}>
                <div className="doc-category">{group}</div>
                {docs.map((doc) => (
                  <div key={doc.id} className={selected?.id === doc.id ? "doc-shell active" : "doc-shell"}>
                    <button className="doc" onClick={() => setSelected(doc)}>
                      <strong>{doc.file_name}</strong>
                      <span>
                        {doc.chunk_count} chunks · {doc.embedding_provider}/{doc.embedding_model}
                      </span>
                    </button>
                    <button
                      className="doc-delete"
                      title="Excluir indexacao"
                      onClick={() => deleteIndexedDocument(doc)}
                      disabled={busy === "delete-document"}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </section>
      </aside>

      <section className="workspace">
        {error && (
          <div className="error">
            <AlertTriangle size={16} />
            <span>{error}</span>
          </div>
        )}
        {job && <ProgressPanel job={job} />}
        {selected && (
          <div className="save-strip">
            <input value={category} onChange={(event) => setCategory(event.target.value)} placeholder="Categoria" />
            <input value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Notas da biblioteca" />
            <button className="text-action" title="Gerar MP4 compativel" onClick={convertMedia} disabled={busy === "media"}>
              {busy === "media" ? <RefreshCcw className="spin" size={16} /> : "MP4"}
            </button>
            <button title="Salvar categoria e notas" onClick={saveDocument} disabled={busy === "save"}>
              {busy === "save" ? <RefreshCcw className="spin" size={16} /> : <Save size={16} />}
            </button>
          </div>
        )}
        <div className="video-grid">
          <section className="video-panel">
            {selected ? (
              <>
                <video
                  key={videoKey}
                  ref={videoRef}
                  controls
                  src={mediaUrl}
                  onLoadedMetadata={(event) => {
                    if (event.currentTarget.videoWidth === 0 && selected) {
                      setVideoWarning("O navegador carregou audio, mas nao conseguiu decodificar a imagem deste video.");
                    }
                  }}
                  onError={() => setVideoWarning("O navegador nao conseguiu abrir este codec de video.")}
                  onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
                />
                {videoWarning && (
                  <div className="video-warning">
                    <AlertTriangle size={15} />
                    <span>{videoWarning}</span>
                    <button onClick={convertMedia} disabled={busy === "media"}>Gerar MP4 H.264</button>
                  </div>
                )}
                <div className="now-line">
                  <span>{formatTime(currentTime)}</span>
                  <strong>{activeCue?.text ?? selected.file_name}</strong>
                </div>
              </>
            ) : (
              <div className="empty-state">Selecione ou indexe um video.</div>
            )}
          </section>

          <section className="topics-panel">
            <div className="section-heading split-heading">
              <div className="panel-tabs" role="tablist" aria-label="Navegacao de topicos">
                <button className={topicTab === "topics" ? "active" : ""} type="button" onClick={() => setTopicTab("topics")}>Topicos</button>
                <button className={topicTab === "summary" ? "active" : ""} type="button" onClick={() => setTopicTab("summary")}>Resumo IA</button>
              </div>
              <div className="heading-actions">
                <button className="summary-action" title="Gerar resumo da apresentacao" onClick={summarizePresentation} disabled={!selected || busy === "summary"}>
                  {busy === "summary" ? <RefreshCcw className="spin" size={14} /> : <FileVideo size={14} />}
                  <span>Gerar</span>
                </button>
                <button title="Sumarizar topicos" onClick={summarizeTopics} disabled={!selected || busy === "topics"}>
                  <RefreshCcw className={busy === "topics" ? "spin" : ""} size={14} />
                </button>
              </div>
            </div>
            {topicTab === "summary" ? (
              <div className="summary-box">
                {presentationSummary ? (
                  <MarkdownContent text={presentationSummary} onJump={jumpTo} />
                ) : (
                  <div className="summary-empty">Clique em Gerar para criar o resumo navegavel via DeepSeek.</div>
                )}
              </div>
            ) : (
              <div className="topic-list">
                {topics.map((topic) => (
                  <button key={topic.id} className="topic" onClick={() => jumpTo(topic.start_seconds)}>
                    <span>{formatTime(topic.start_seconds)}</span>
                    <strong>{topic.title}</strong>
                    <small>{topic.summary}</small>
                  </button>
                ))}
              </div>
            )}
          </section>
        </div>

        <div className="bottom-grid">
          <section className="transcript-panel">
            <div className="section-heading split-heading">
              <span>SRT</span>
              <small>{filteredTranscript.length}/{transcript.length}</small>
            </div>
            <div className="srt-search-row">
              <Search size={15} />
              <input value={srtSearch} onChange={(event) => setSrtSearch(event.target.value)} placeholder="Pesquisar no SRT" />
              {srtSearch && <button className="text-action" onClick={() => setSrtSearch("")}>Limpar</button>}
            </div>
            <div className="transcript-list">
              {filteredTranscript.map((cue) => (
                <button
                  key={cue.cue_index}
                  className={activeCue?.cue_index === cue.cue_index ? "cue active" : "cue"}
                  onClick={() => jumpTo(cue.start_seconds)}
                >
                  <span>{formatTime(cue.start_seconds)}</span>
                  <p>{cue.text}</p>
                </button>
              ))}
            </div>
          </section>

          <section className="chat-panel">
            <div className="section-heading split-heading">
              <span>Chat Cloud</span>
              <small>{llmProvider === "groq" ? `Groq ${groqLlmModel === "groq/compound-mini" ? "Compound Mini" : "Llama 4 Scout"}` : "DeepSeek"}</small>
            </div>
            <div className="messages" ref={messagesRef}>
              {chat.map((message, index) => (
                <article key={index} className={`message ${message.role}`}>
                  <MessageContent text={message.text} sources={message.sources} onJump={jumpTo} />
                  {message.sources?.map((source) => (
                    <button key={source.chunk_id} className="source" onClick={() => jumpTo(source.start_seconds)}>
                      <SkipForward size={14} />
                      <span>
                        {source.file_name} · {formatTime(source.start_seconds)} · {source.score.toFixed(3)}
                      </span>
                    </button>
                  ))}
                </article>
              ))}
            </div>
            <form onSubmit={ask} className="ask-row">
              <input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={`Pergunta via ${llmProvider === "groq" ? "Groq" : "DeepSeek"}`} />
              <button disabled={busy === "ask"} title="Enviar">
                {busy === "ask" ? <RefreshCcw className="spin" size={16} /> : <Send size={16} />}
              </button>
            </form>
          </section>
        </div>
      </section>
      {configOpen && (
        <ConfigDialog
          busy={busy}
          deepseekApiKey={deepseekApiKey}
          deepseekStatus={deepseekSecretStatus}
          groqApiKey={groqApiKey}
          groqStatus={groqSecretStatus}
          llmProvider={llmProvider}
          groqLlmModel={groqLlmModel}
          longSummaryMode={longSummaryMode}
          onClose={() => setConfigOpen(false)}
          onDeepseekChange={setDeepseekApiKey}
          onGroqChange={setGroqApiKey}
          onLlmProviderChange={setLlmProvider}
          onGroqLlmModelChange={setGroqLlmModel}
          onLongSummaryModeChange={setLongSummaryMode}
          onSave={saveApiKey}
          onDelete={deleteApiKey}
        />
      )}
      {transcriptionOpen && (
        <TranscriptionDialog
          busy={busy === "index"}
          filePath={path.trim()}
          reindex={reindex}
          provider={transcriptionProvider}
          whisperModel={whisperModel}
          whisperCpuThreads={whisperCpuThreads}
          groqConfigured={Boolean(groqSecretStatus?.configured)}
          onClose={() => setTranscriptionOpen(false)}
          onReindexChange={setReindex}
          onProviderChange={setTranscriptionProvider}
          onWhisperModelChange={setWhisperModel}
          onWhisperCpuThreadsChange={setWhisperCpuThreads}
          onOpenConfig={() => {
            setTranscriptionOpen(false);
            setConfigOpen(true);
          }}
          onStart={indexVideo}
        />
      )}
    </main>
  );
}


function TranscriptionDialog({
  busy,
  filePath,
  reindex,
  provider,
  whisperModel,
  whisperCpuThreads,
  groqConfigured,
  onClose,
  onReindexChange,
  onProviderChange,
  onWhisperModelChange,
  onWhisperCpuThreadsChange,
  onOpenConfig,
  onStart,
}: {
  busy: boolean;
  filePath: string;
  reindex: boolean;
  provider: TranscriptionProvider;
  whisperModel: WhisperModelName;
  whisperCpuThreads: number;
  groqConfigured: boolean;
  onClose: () => void;
  onReindexChange: (value: boolean) => void;
  onProviderChange: (value: TranscriptionProvider) => void;
  onWhisperModelChange: (value: WhisperModelName) => void;
  onWhisperCpuThreadsChange: (value: number) => void;
  onOpenConfig: () => void;
  onStart: () => void;
}) {
  const usingGroqWithoutKey = provider === "groq" && !groqConfigured;
  return (
    <div className="modal-backdrop" role="presentation">
      <section className="config-modal transcription-modal" role="dialog" aria-modal="true" aria-label="Transcrever video">
        <div className="config-head">
          <div>
            <strong>Transcrever</strong>
            <span title={filePath}>{filePath}</span>
          </div>
          <button type="button" title="Fechar" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        <div className="provider-options">
          <button type="button" className={provider === "local" ? "active" : ""} onClick={() => onProviderChange("local")}>
            <strong>Local</strong>
            <span>faster-whisper no computador</span>
          </button>
          <button type="button" className={provider === "groq" ? "active" : ""} onClick={() => onProviderChange("groq")}>
            <strong>Groq</strong>
            <span>whisper-large-v3-turbo</span>
          </button>
        </div>

        {provider === "local" ? (
          <div className="transcription-form">
            <label className="check-row">
              <input type="checkbox" checked={reindex} onChange={(event) => onReindexChange(event.target.checked)} />
              <span>Reindexar video existente</span>
            </label>
            <label className="model-control">
              <span>Modelo local</span>
              <select value={whisperModel} onChange={(event) => onWhisperModelChange(event.target.value as WhisperModelName)}>
                <option value="tiny">tiny</option>
                <option value="base">base</option>
                <option value="small">small</option>
                <option value="medium">medium</option>
                <option value="large-v3">large-v3</option>
              </select>
            </label>
            <label className="thread-control">
              <span>Threads Whisper</span>
              <input
                type="number"
                min="0"
                max="64"
                step="1"
                value={whisperCpuThreads}
                onChange={(event) => onWhisperCpuThreadsChange(clampNumber(event.target.value, 0, 64))}
                title="0 usa o modo automatico do faster-whisper"
              />
            </label>
          </div>
        ) : (
          <div className="transcription-form groq-only">
            <label className="check-row">
              <input type="checkbox" checked={reindex} onChange={(event) => onReindexChange(event.target.checked)} />
              <span>Reindexar video existente</span>
            </label>
          </div>
        )}

        <div className={usingGroqWithoutKey ? "provider-note warning" : "provider-note"}>
          {provider === "groq"
            ? "Groq comprime o audio para upload abaixo de 25 MB, transcreve na API e salva SRT com timestamps."
            : "Local usa faster-whisper e mantem o audio no computador."}
        </div>

        <div className="modal-actions">
          {usingGroqWithoutKey && <button className="text-action" type="button" onClick={onOpenConfig}>Configurar Groq</button>}
          <button className="text-action" type="button" onClick={onClose}>Cancelar</button>
          <button type="button" onClick={onStart} disabled={busy || usingGroqWithoutKey}>
            {busy ? <RefreshCcw className="spin" size={15} /> : <Play size={15} />}
            <span>Iniciar</span>
          </button>
        </div>
      </section>
    </div>
  );
}

function ConfigDialog({
  busy,
  deepseekApiKey,
  deepseekStatus,
  groqApiKey,
  groqStatus,
  llmProvider,
  groqLlmModel,
  longSummaryMode,
  onClose,
  onDeepseekChange,
  onGroqChange,
  onLlmProviderChange,
  onGroqLlmModelChange,
  onLongSummaryModeChange,
  onSave,
  onDelete,
}: {
  busy: string;
  deepseekApiKey: string;
  deepseekStatus: SecretStatus | null;
  groqApiKey: string;
  groqStatus: SecretStatus | null;
  llmProvider: LlmProvider;
  groqLlmModel: GroqLlmModel;
  longSummaryMode: LongSummaryMode;
  onClose: () => void;
  onDeepseekChange: (value: string) => void;
  onGroqChange: (value: string) => void;
  onLlmProviderChange: (value: LlmProvider) => void;
  onGroqLlmModelChange: (value: GroqLlmModel) => void;
  onLongSummaryModeChange: (value: LongSummaryMode) => void;
  onSave: (provider: "deepseek" | "groq", value: string) => void;
  onDelete: (provider: "deepseek" | "groq") => void;
}) {
  return (
    <div className="modal-backdrop" role="presentation">
      <section className="config-modal" role="dialog" aria-modal="true" aria-label="Configurar APIs">
        <div className="config-head">
          <strong>Config</strong>
          <button type="button" title="Fechar" onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        <div className="secret-editor">
          <div className="secret-status">
            <strong>IA para chat</strong>
            <span>{llmProvider === "groq" ? (groqLlmModel === "groq/compound-mini" ? "Groq Compound Mini" : "Groq Llama 4 Scout") : "DeepSeek"}</span>
          </div>
          <div className="provider-options compact">
            <button type="button" className={llmProvider === "groq" ? "active" : ""} onClick={() => onLlmProviderChange("groq")}>
              <strong>Groq</strong>
              <span>Llama 4 Scout 128K</span>
            </button>
            <button type="button" className={llmProvider === "deepseek" ? "active" : ""} onClick={() => onLlmProviderChange("deepseek")}>
              <strong>DeepSeek</strong>
              <span>Modelo configurado</span>
            </button>
          </div>
          {llmProvider === "groq" && (
            <label className="model-control config-select">
              <span>Modelo Groq</span>
              <select value={groqLlmModel} onChange={(event) => onGroqLlmModelChange(event.target.value as GroqLlmModel)}>
                <option value="meta-llama/llama-4-scout-17b-16e-instruct">Llama 4 Scout 128K</option>
                <option value="groq/compound-mini">Compound Mini 128K</option>
              </select>
            </label>
          )}
        </div>
        <div className="secret-editor">
          <div className="secret-status">
            <strong>Resumo/topicos longos</strong>
            <span>{longSummaryModeLabel(longSummaryMode)}</span>
          </div>
          <div className="provider-options compact summary-mode-options">
            <button type="button" className={longSummaryMode === "deepseek_full" ? "active" : ""} onClick={() => onLongSummaryModeChange("deepseek_full")}>
              <strong>DeepSeek inteiro</strong>
              <span>Uma chamada com o transcript completo</span>
            </button>
            <button type="button" className={longSummaryMode === "groq_full" ? "active" : ""} onClick={() => onLongSummaryModeChange("groq_full")}>
              <strong>Groq inteiro</strong>
              <span>Tenta uma chamada compacta</span>
            </button>
            <button type="button" className={longSummaryMode === "groq_chunked" ? "active" : ""} onClick={() => onLongSummaryModeChange("groq_chunked")}>
              <strong>Groq por blocos</strong>
              <span>Divide e consolida por topicos</span>
            </button>
          </div>
        </div>
        <SecretEditor
          label="DeepSeek"
          provider="deepseek"
          placeholder="Colar DeepSeek API key"
          value={deepseekApiKey}
          status={deepseekStatus}
          busy={busy === "secret-deepseek"}
          onChange={onDeepseekChange}
          onSave={onSave}
          onDelete={onDelete}
        />
        <SecretEditor
          label="Groq"
          provider="groq"
          placeholder="Colar Groq API key"
          value={groqApiKey}
          status={groqStatus}
          busy={busy === "secret-groq"}
          onChange={onGroqChange}
          onSave={onSave}
          onDelete={onDelete}
        />
      </section>
    </div>
  );
}

function SecretEditor({
  label,
  provider,
  placeholder,
  value,
  status,
  busy,
  onChange,
  onSave,
  onDelete,
}: {
  label: string;
  provider: "deepseek" | "groq";
  placeholder: string;
  value: string;
  status: SecretStatus | null;
  busy: boolean;
  onChange: (value: string) => void;
  onSave: (provider: "deepseek" | "groq", value: string) => void;
  onDelete: (provider: "deepseek" | "groq") => void;
}) {
  return (
    <div className="secret-editor">
      <div className="secret-status">
        <strong>{label}</strong>
        <span>{status?.configured ? `Salva: ${status.masked}` : "API key nao salva"}</span>
      </div>
      <div className="cloud-key-row">
        <input
          type="password"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          autoComplete="off"
          spellCheck={false}
        />
        <button className="text-action" type="button" onClick={() => onSave(provider, value)} disabled={busy || !value.trim()}>
          {busy ? <RefreshCcw className="spin" size={14} /> : "Salvar"}
        </button>
        <button className="text-action danger" type="button" onClick={() => onDelete(provider)} disabled={busy || !status?.configured}>Apagar</button>
      </div>
    </div>
  );
}

function longSummaryModeLabel(value: LongSummaryMode) {
  if (value === "groq_full") return "Groq inteiro";
  if (value === "groq_chunked") return "Groq por blocos";
  return "DeepSeek inteiro";
}


function MessageContent({ text, sources, onJump }: { text: string; sources?: SourceHit[]; onJump?: (seconds: number) => void }) {
  return <MarkdownContent text={text} sources={sources} onJump={onJump} />;
}

function MarkdownContent({ text, sources, onJump }: { text: string; sources?: SourceHit[]; onJump?: (seconds: number) => void }) {
  const blocks = normalizeMarkdown(text).split(/\n{2,}/).map((block) => block.trim()).filter(Boolean);
  return (
    <div className="message-content summary-content">
      {blocks.map((block, index) => {
        const heading = block.match(/^(#{1,3})\s+(.+)$/);
        if (heading) return <strong className="markdown-heading" key={index}>{renderInlineMarkdown(heading[2], onJump, sources)}</strong>;
        const lines = block.split("\n").map((line) => line.trim()).filter(Boolean);
        const isList = lines.length > 0 && lines.every((line) => /^([-*]|\d+[.)])\s+/.test(line));
        if (isList) {
          return (
            <ul key={index}>
              {lines.map((line, lineIndex) => (
                <li key={lineIndex}>{renderInlineMarkdown(line.replace(/^([-*]|\d+[.)])\s+/, ""), onJump, sources)}</li>
              ))}
            </ul>
          );
        }
        return <p key={index}>{renderInlineMarkdown(block, onJump, sources)}</p>;
      })}
    </div>
  );
}

function normalizeMarkdown(text: string) {
  return text
    .replace(/\r\n/g, "\n")
    .replace(/^(#{1,3}\s+Resumo IA)\s+/i, "$1\n\n")
    .replace(/\s+[-*]\s+(?=\*\*|\[[^\]]+\]\(#t=|\(?#t=|(?:\d{1,2}:)?\d{1,2}:\d{2}\s+\*\*|[A-ZÁÉÍÓÚÂÊÔÃÕÀÇ][^:]{3,80}:)/g, "\n- ")
    .replace(/(\[[^\]]+\]\(#t=[0-9.]+[\])])\s*[-–]\s*/g, "$1\n- ")
    .replace(/(\(#t=[0-9.]+\)|#t=[0-9.]+|(?:\d{1,2}:)?\d{1,2}:\d{2})\s*[-–]\s+(?=(?:\d{1,2}:)?\d{1,2}:\d{2}|\[[^\]]+\]\(#t=|\*\*)/g, "$1\n- ")
    .trim();
}

function renderInlineMarkdown(text: string, onJump?: (seconds: number) => void, sources?: SourceHit[]) {
  const parts = text.split(/(\[[^\]]+\]\(#t=[0-9.]+[\])]|\[[0-9]+\]|\(?#t=[0-9.]+\)?|[0-9]+(?:\.[0-9]+)?s(?:\s*[-–]\s*[0-9]+(?:\.[0-9]+)?s)?|(?:\d{1,2}:)?\d{1,2}:\d{2}(?=\s+\*\*|\b)|`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g).filter(Boolean);
  return parts.map((part, index) => {
    const timeLink = parseTimeLink(part);
    if (timeLink) {
      return (
        <button className="time-link" type="button" key={index} onClick={() => onJump?.(timeLink.seconds)}>
          {timeLink.label}
        </button>
      );
    }
    const sourceLink = parseSourceLink(part, sources);
    if (sourceLink) {
      return (
        <button className="source-link" type="button" key={index} onClick={() => onJump?.(sourceLink.seconds)}>
          {sourceLink.label}
        </button>
      );
    }
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("*") && part.endsWith("*")) {
      return <em key={index}>{part.slice(1, -1)}</em>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={index}>{part.slice(1, -1)}</code>;
    }
    return part;
  });
}

function parseSourceLink(part: string, sources?: SourceHit[]): { label: string; seconds: number } | null {
  const match = part.match(/^\[([0-9]+)\]$/);
  if (!match || !sources) return null;
  const sourceIndex = Number(match[1]) - 1;
  const source = sources[sourceIndex];
  if (!source) return null;
  return { label: `[${match[1]} · ${formatTime(source.start_seconds)}]`, seconds: source.start_seconds };
}

function parseTimeLink(part: string): { label: string; seconds: number } | null {
  const markdown = part.match(/^\[([^\]]+)\]\(#t=([0-9.]+)[\])]$/);
  if (markdown) return { label: markdown[1], seconds: Number(markdown[2]) };

  const naked = part.match(/^\(?#t=([0-9.]+)\)?$/);
  if (naked) {
    const seconds = Number(naked[1]);
    return { label: formatTime(seconds), seconds };
  }

  const plainTime = part.match(/^((?:\d{1,2}:)?\d{1,2}:\d{2})$/);
  if (plainTime) return { label: plainTime[1], seconds: parseTimestampSeconds(plainTime[1]) };

  const secondsTime = part.match(/^([0-9]+(?:\.[0-9]+)?)s(?:\s*[-–]\s*([0-9]+(?:\.[0-9]+)?)s)?$/);
  if (secondsTime) {
    const seconds = Number(secondsTime[1]);
    return { label: secondsTime[2] ? `${formatTime(seconds)}-${formatTime(Number(secondsTime[2]))}` : formatTime(seconds), seconds };
  }

  return null;
}

function parseTimestampSeconds(value: string) {
  const parts = value.split(":").map(Number);
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  return 0;
}

function ProgressPanel({ job }: { job: JobState }) {
  const icon = job.status === "completed" ? <CheckCircle2 size={18} /> : job.status === "failed" ? <AlertTriangle size={18} /> : <Activity size={18} />;
  const latestLogs = job.logs.slice(-8).reverse();
  return (
    <section className={`progress-panel ${job.status}`}>
      <div className="progress-head">
        <div className="progress-title">
          {icon}
          <div>
            <strong>{job.message}</strong>
            <span>{job.phase} · {job.status}</span>
          </div>
        </div>
        <div className="progress-percent">{Math.round(job.percent)}%</div>
      </div>
      <div className="progress-track">
        <div className="progress-fill" style={{ width: `${job.percent}%` }} />
      </div>
      <div className="progress-detail">
        <Cpu size={15} />
        <span>{job.detail || "Backend preparando a proxima etapa"}</span>
      </div>
      <div className="progress-log">
        {latestLogs.map((log, index) => (
          <div className="log-line" key={`${log.time}-${index}`}>
            <Database size={13} />
            <span className="log-time">{new Date(log.time).toLocaleTimeString()}</span>
            <strong>{Math.round(log.percent)}%</strong>
            <span>{log.message}</span>
            <small>{log.detail}</small>
          </div>
        ))}
      </div>
    </section>
  );
}

function clampNumber(value: string, min: number, max: number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return min;
  return Math.max(min, Math.min(max, Math.floor(parsed)));
}

function formatTime(seconds: number) {
  const safe = Math.max(0, Math.floor(seconds));
  const hrs = Math.floor(safe / 3600);
  const mins = Math.floor((safe % 3600) / 60);
  const secs = safe % 60;
  return hrs > 0
    ? `${hrs}:${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`
    : `${mins}:${String(secs).padStart(2, "0")}`;
}
