import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Activity, AlertTriangle, CheckCircle2, Cpu, Database, FileVideo, FolderOpen, Play, RefreshCcw, Save, Search, Send, SkipForward } from "lucide-react";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

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

type SecretStatus = {
  provider: string;
  configured: boolean;
  masked: string | null;
  storage: string;
};

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
  const [question, setQuestion] = useState("");
  const [chat, setChat] = useState<ChatMessage[]>([]);
  const [cloudApiKey, setCloudApiKey] = useState("");
  const [srtSearch, setSrtSearch] = useState("");
  const [secretStatus, setSecretStatus] = useState<SecretStatus | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [currentTime, setCurrentTime] = useState(0);
  const [reindex, setReindex] = useState(false);
  const [category, setCategory] = useState("Sem categoria");
  const [notes, setNotes] = useState("");
  const [job, setJob] = useState<JobState | null>(null);
  const [videoWarning, setVideoWarning] = useState("");

  useEffect(() => {
    loadDocuments();
    loadFolder();
    loadSecretStatus();
  }, []);

  useEffect(() => {
    if (!selected) return;
    setCategory(selected.category || "Sem categoria");
    setNotes(selected.notes || "");
    setVideoWarning("");
    Promise.all([loadTranscript(selected.id), loadTopics(selected.id)]).catch(showError);
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

  async function loadDocuments() {
    setDocuments(await api<DocumentItem[]>("/documents"));
  }

  async function loadFolder(nextPath?: string) {
    const suffix = nextPath ? `?path=${encodeURIComponent(nextPath)}` : "";
    const result = await api<{ path: string; parent: string | null; entries: FileEntry[] }>(`/files/list${suffix}`);
    setFolder(result.path);
    setParent(result.parent);
    setEntries(result.entries);
  }

  async function loadTranscript(documentId: number) {
    setTranscript(await api<TranscriptCue[]>(`/documents/${documentId}/transcript`));
  }

  async function loadTopics(documentId: number) {
    setTopics(await api<Topic[]>(`/documents/${documentId}/topics`));
  }

  async function loadSecretStatus() {
    setSecretStatus(await api<SecretStatus>("/settings/secrets/deepseek"));
  }

  async function saveCloudApiKey() {
    if (!cloudApiKey.trim()) return;
    setBusy("secret");
    setError("");
    try {
      setSecretStatus(await api<SecretStatus>("/settings/secrets/deepseek", {
        method: "POST",
        body: JSON.stringify({ api_key: cloudApiKey.trim() }),
      }));
      setCloudApiKey("");
    } catch (err) {
      showError(err);
    } finally {
      setBusy("");
    }
  }

  async function deleteCloudApiKey() {
    setBusy("secret");
    setError("");
    try {
      setSecretStatus(await api<SecretStatus>("/settings/secrets/deepseek", { method: "DELETE" }));
      setCloudApiKey("");
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
      setTopics(await api<Topic[]>(`/documents/${selected.id}/topics/summarize`, { method: "POST" }));
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
    try {
      const result = await api<{ job_id: string }>("/videos/index/jobs", {
        method: "POST",
        body: JSON.stringify({ path: path.trim(), reindex, transcribe: true, category }),
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
          history,
          cloud_api_key: cloudApiKey.trim() || null,
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
          <FileVideo size={20} />
          <span>Video RAG</span>
        </div>
        <div className="system-badge">
          <span className="pulse" />
          <span>Local SQLite · Whisper Small · RAG</span>
        </div>

        <section className="panel">
          <div className="panel-title">
            <FolderOpen size={16} />
            <span>Arquivos</span>
          </div>
          <div className="path-row">
            <input value={path} onChange={(event) => setPath(event.target.value)} placeholder="/caminho/video.mp4" />
            <button title="Indexar" onClick={indexVideo} disabled={busy === "index"}>
              {busy === "index" ? <RefreshCcw className="spin" size={16} /> : <Play size={16} />}
            </button>
          </div>
          <input value={category} onChange={(event) => setCategory(event.target.value)} placeholder="Categoria" />
          <label className="check-row">
            <input type="checkbox" checked={reindex} onChange={(event) => setReindex(event.target.checked)} />
            <span>Reindexar</span>
          </label>
          <div className="folder-bar">
            <button onClick={() => parent && loadFolder(parent)} disabled={!parent}>
              ..
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
                  <button
                    key={doc.id}
                    className={selected?.id === doc.id ? "doc active" : "doc"}
                    onClick={() => setSelected(doc)}
                  >
                    <strong>{doc.file_name}</strong>
                    <span>
                      {doc.chunk_count} chunks · {doc.embedding_provider}/{doc.embedding_model}
                    </span>
                  </button>
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
              <span>Topicos</span>
              <button title="Sumarizar topicos" onClick={summarizeTopics} disabled={!selected || busy === "topics"}>
                <RefreshCcw className={busy === "topics" ? "spin" : ""} size={14} />
              </button>
            </div>
            <div className="topic-list">
              {topics.map((topic) => (
                <button key={topic.id} className="topic" onClick={() => jumpTo(topic.start_seconds)}>
                  <span>{formatTime(topic.start_seconds)}</span>
                  <strong>{topic.title}</strong>
                  <small>{topic.summary}</small>
                </button>
              ))}
            </div>
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
              <small>DeepSeek</small>
            </div>
            <div className="cloud-secret-box">
              <div className="secret-status">
                <span>{secretStatus?.configured ? `DeepSeek salva: ${secretStatus.masked}` : "DeepSeek API key nao salva"}</span>
                {secretStatus?.configured && <button className="text-action danger" type="button" onClick={deleteCloudApiKey} disabled={busy === "secret"}>Apagar API_KEY</button>}
              </div>
              <div className="cloud-key-row">
                <input
                  type="password"
                  value={cloudApiKey}
                  onChange={(event) => setCloudApiKey(event.target.value)}
                  placeholder="Colar DeepSeek API key para salvar criptografada"
                  autoComplete="off"
                  spellCheck={false}
                />
                <button className="text-action" type="button" onClick={saveCloudApiKey} disabled={busy === "secret" || !cloudApiKey.trim()}>Salvar</button>
                <button className="text-action" type="button" onClick={() => setCloudApiKey("")}>Limpar</button>
              </div>
            </div>
            <div className="messages" ref={messagesRef}>
              {chat.map((message, index) => (
                <article key={index} className={`message ${message.role}`}>
                  <MessageContent text={message.text} />
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
              <input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Pergunta via DeepSeek" />
              <button disabled={busy === "ask"} title="Enviar">
                {busy === "ask" ? <RefreshCcw className="spin" size={16} /> : <Send size={16} />}
              </button>
            </form>
          </section>
        </div>
      </section>
    </main>
  );
}



function MessageContent({ text }: { text: string }) {
  const blocks = text.split(/\n{2,}/).map((block) => block.trim()).filter(Boolean);
  return (
    <div className="message-content">
      {blocks.map((block, index) => {
        const lines = block.split("\n").map((line) => line.trim()).filter(Boolean);
        const isList = lines.length > 0 && lines.every((line) => /^([-*]|\d+[.)])\s+/.test(line));
        if (isList) {
          return (
            <ul key={index}>
              {lines.map((line, lineIndex) => (
                <li key={lineIndex}>{renderInlineMarkdown(line.replace(/^([-*]|\d+[.)])\s+/, ""))}</li>
              ))}
            </ul>
          );
        }
        return <p key={index}>{renderInlineMarkdown(block)}</p>;
      })}
    </div>
  );
}

function renderInlineMarkdown(text: string) {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g).filter(Boolean);
  return parts.map((part, index) => {
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

function formatTime(seconds: number) {
  const safe = Math.max(0, Math.floor(seconds));
  const hrs = Math.floor(safe / 3600);
  const mins = Math.floor((safe % 3600) / 60);
  const secs = safe % 60;
  return hrs > 0
    ? `${hrs}:${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`
    : `${mins}:${String(secs).padStart(2, "0")}`;
}
