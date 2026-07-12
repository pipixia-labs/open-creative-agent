import { useCallback, useEffect, useMemo, useState } from "react";
import { createSession, streamChat } from "./api";
import ChatPanel from "./components/ChatPanel";
import { PlusIcon } from "./components/icons";
import MediaCanvas from "./components/MediaCanvas";
import type { CanvasMedia, ChatMessage, FinalPayload, SessionPayload } from "./types";

const LOCAL_USERNAME = "local";
const DOCUMENT_EXTENSIONS = new Set([
  ".pdf",
  ".doc",
  ".docx",
  ".ppt",
  ".pptx",
  ".xls",
  ".xlsx",
  ".csv",
  ".txt",
  ".md",
  ".zip",
]);

export default function App() {
  const [session, setSession] = useState<SessionPayload | null>(null);
  const [status, setStatus] = useState("Creating local session");
  const [statusMode, setStatusMode] = useState<"ready" | "running" | "done" | "error">("running");
  const [isLoading, setIsLoading] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([welcomeMessage()]);
  const [mediaItems, setMediaItems] = useState<CanvasMedia[]>([]);

  const sessionPreview = useMemo(() => shortSessionId(session?.session_id), [session?.session_id]);

  const startSession = useCallback(async () => {
    setStatus("Creating local session");
    setStatusMode("running");
    const payload = await createSession(LOCAL_USERNAME);
    setSession(payload);
    const preview = shortSessionId(payload.session_id);
    setStatus(preview);
    setStatusMode("ready");
    return payload;
  }, []);

  const resetSession = useCallback(async () => {
    if (isLoading) return;
    setMessages([welcomeMessage()]);
    setMediaItems([]);
    try {
      await startSession();
    } catch (error) {
      setStatus("Session creation failed");
      setStatusMode("error");
      setMessages([errorMessage(error)]);
    }
  }, [isLoading, startSession]);

  useEffect(() => {
    startSession().catch((error) => {
      setStatus("Session creation failed");
      setStatusMode("error");
      setMessages([errorMessage(error)]);
    });
  }, [startSession]);

  const handleSend = useCallback(
    async (prompt: string, files: File[]) => {
      if (isLoading || (!prompt && files.length === 0)) return;

      const userMessage: ChatMessage = {
        id: createId("user"),
        role: "user",
        content: prompt || "Files attached.",
        status: "done",
        steps: [],
        stepsOpen: false,
        files: files.map((file) => ({ name: file.name })),
        media: [],
        filenames: [],
      };
      const assistantId = createId("assistant");
      const assistantMessage: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        status: "running",
        steps: [],
        stepsOpen: true,
        files: [],
        media: [],
        filenames: [],
      };

      setMessages((current) => [
        ...current.filter((message) => message.id !== "welcome"),
        userMessage,
        assistantMessage,
      ]);
      setIsLoading(true);
      setStatus("Agent running");
      setStatusMode("running");

      try {
        const activeSession = session ?? (await startSession());
        const data = new FormData();
        data.append("message", prompt);
        data.append("session_id", activeSession.session_id);
        data.append("user_id", activeSession.user_id);
        data.append("username", LOCAL_USERNAME);

        for (const file of files) {
          if (isImageFile(file)) {
            data.append("images", file, file.name);
          } else if (isSupportedDocument(file)) {
            data.append("documents", file, file.name);
          }
        }

        await streamChat(data, (event) => {
          if (event.type === "step") {
            appendStep(assistantId, event.content);
          }
          if (event.type === "final") {
            applyFinal(assistantId, event.content);
            setStatus("Task completed");
            setStatusMode("done");
          }
          if (event.type === "error") {
            applyError(assistantId, event.content);
            setStatus("Task failed");
            setStatusMode("error");
          }
        });
      } catch (error) {
        applyError(assistantId, error);
        setStatus("Task failed");
        setStatusMode("error");
      } finally {
        setIsLoading(false);
      }
    },
    [isLoading, session, startSession],
  );

  const appendStep = (messageId: string, content: unknown) => {
    const step = typeof content === "string" ? content : JSON.stringify(content, null, 2);
    setMessages((current) =>
      current.map((message) =>
        message.id === messageId
          ? { ...message, status: "running", steps: [...message.steps, step], stepsOpen: true }
          : message,
      ),
    );
  };

  const applyFinal = (messageId: string, content: unknown) => {
    const payload = normalizeFinalPayload(content);
    const media = (payload.image || [])
      .map((source, index) => {
        const src = normalizeMediaSource(source);
        if (!src) return null;
        const kind = src.startsWith("data:video") ? "mp4" : "png";
        return {
          id: createId("media"),
          src,
          name: `generated-${Date.now()}-${index + 1}.${kind}`,
        };
      })
      .filter((item): item is CanvasMedia => item !== null);

    setMediaItems((current) => [...current, ...media]);
    setMessages((current) =>
      current.map((message) =>
        message.id === messageId
          ? {
              ...message,
              content: payload.text || payload.final_output_text || "Task completed.",
              status: "done",
              stepsOpen: false,
              media,
              filenames: Array.isArray(payload.filenames) ? payload.filenames : [],
            }
          : message,
      ),
    );
  };

  const applyError = (messageId: string, content: unknown) => {
    const text = content instanceof Error ? content.message : typeof content === "string" ? content : JSON.stringify(content);
    setMessages((current) =>
      current.map((message) =>
        message.id === messageId
          ? {
              ...message,
              content: text,
              status: "error",
              stepsOpen: false,
            }
          : message,
      ),
    );
  };

  const handleDownload = useCallback(
    async (filename: string) => {
      if (!session) return;
      const params = new URLSearchParams({
        session_id: session.session_id,
        filename,
        user_id: session.user_id,
      });
      const response = await fetch(`/file/download?${params.toString()}`);
      if (!response.ok) {
        setMessages((current) => [...current, errorMessage(`Download failed: ${response.status}`)]);
        return;
      }
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(objectUrl);
    },
    [session],
  );

  const toggleSteps = (messageId: string) => {
    setMessages((current) =>
      current.map((message) =>
        message.id === messageId ? { ...message, stepsOpen: !message.stepsOpen } : message,
      ),
    );
  };

  return (
    <main className="workspace-layout" aria-label="Open Creative Agent workspace">
      <section className="canvas-pane" aria-label="Media canvas">
        <header className="top-bar">
          <div className="brand">
            <button className="icon-button" type="button" title="New session" aria-label="New session" onClick={resetSession} disabled={isLoading}>
              <PlusIcon />
            </button>
            <div className="title-group">
              <h1 className="title">Open Creative Agent</h1>
              <p className="subtitle">Creative Workspace</p>
            </div>
          </div>
          <div className={`status-pill ${statusMode}`}>
            <span className="status-dot" />
            <span className="status-text">{status}</span>
          </div>
        </header>
        <MediaCanvas mediaItems={mediaItems} />
      </section>

      <ChatPanel
        messages={messages}
        isLoading={isLoading}
        sessionPreview={sessionPreview}
        onCreateSession={resetSession}
        onDownload={handleDownload}
        onSend={handleSend}
        onToggleSteps={toggleSteps}
      />
    </main>
  );
}

function welcomeMessage(): ChatMessage {
  return {
    id: "welcome",
    role: "assistant",
    content: "Tell me what you want to create, analyze, or refine. Generated media will appear on the canvas.",
    status: "idle",
    steps: [],
    stepsOpen: false,
    files: [],
    media: [],
    filenames: [],
  };
}

function errorMessage(error: unknown): ChatMessage {
  return {
    id: createId("error"),
    role: "assistant",
    content: error instanceof Error ? error.message : String(error),
    status: "error",
    steps: [],
    stepsOpen: false,
    files: [],
    media: [],
    filenames: [],
  };
}

function createId(prefix: string): string {
  if ("crypto" in window && "randomUUID" in window.crypto) {
    return `${prefix}-${window.crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function shortSessionId(sessionId?: string): string {
  if (!sessionId) return "Local mode";
  return `Session ${sessionId.slice(0, 8)}...${sessionId.slice(-5)}`;
}

function fileExtension(name: string): string {
  const index = name.lastIndexOf(".");
  return index >= 0 ? name.slice(index).toLowerCase() : "";
}

function isImageFile(file: File): boolean {
  return file.type.startsWith("image/") || [".png", ".jpg", ".jpeg", ".bmp"].includes(fileExtension(file.name));
}

function isSupportedDocument(file: File): boolean {
  return DOCUMENT_EXTENSIONS.has(fileExtension(file.name));
}

function normalizeMediaSource(value: string): string {
  if (!value) return "";
  if (value.startsWith("data:")) return value;
  return `data:image/png;base64,${value}`;
}

function normalizeFinalPayload(content: unknown): FinalPayload {
  if (typeof content === "object" && content !== null) {
    return content as FinalPayload;
  }
  return { text: String(content || "") };
}
