import type { ChatMessage } from "../types";
import { BotIcon, BrainIcon, ChevronIcon, DownloadIcon, NewChatIcon } from "./icons";
import InputArea from "./InputArea";

type ChatPanelProps = {
  messages: ChatMessage[];
  isLoading: boolean;
  sessionPreview: string;
  onCreateSession: () => void;
  onDownload: (filename: string) => void;
  onSend: (prompt: string, files: File[]) => void;
  onToggleSteps: (messageId: string) => void;
};

export default function ChatPanel({
  messages,
  isLoading,
  sessionPreview,
  onCreateSession,
  onDownload,
  onSend,
  onToggleSteps,
}: ChatPanelProps) {
  return (
    <aside className="chat-panel" aria-label="Chat panel">
      <div className="chat-header">
        <div className="chat-heading">
          <h2>Chat</h2>
          <p>{sessionPreview}</p>
        </div>
        <button className="icon-button" type="button" title="Start new chat" aria-label="Start new chat" onClick={onCreateSession} disabled={isLoading}>
          <NewChatIcon />
        </button>
      </div>

      <div className="messages" aria-live="polite">
        {messages.map((message) => (
          <MessageItem
            key={message.id}
            message={message}
            onDownload={onDownload}
            onToggleSteps={onToggleSteps}
          />
        ))}
      </div>

      <InputArea disabled={isLoading} onSend={onSend} />
    </aside>
  );
}

function MessageItem({
  message,
  onDownload,
  onToggleSteps,
}: {
  message: ChatMessage;
  onDownload: (filename: string) => void;
  onToggleSteps: (messageId: string) => void;
}) {
  const isUser = message.role === "user";

  return (
    <div className={`message ${isUser ? "user" : "assistant"}`}>
      {!isUser && (
        <div className="avatar">
          <BotIcon />
        </div>
      )}
      <div className="bubble">
        {message.content ? <p className="bubble-text">{message.content}</p> : null}
        {message.status === "running" && !message.content ? (
          <span className="typing" aria-label="Agent is running">
            <span />
            <span />
            <span />
          </span>
        ) : null}

        {message.files.length > 0 && (
          <div className="file-list">
            {message.files.map((file, index) => (
              <span className="file-chip" key={`${file.name}-${index}`}>
                <span className="chip-name">{file.name}</span>
              </span>
            ))}
          </div>
        )}

        {message.steps.length > 0 && (
          <>
            <button className="thinking-toggle" type="button" onClick={() => onToggleSteps(message.id)}>
              <BrainIcon />
              <span>Thinking process {message.stepsOpen ? "Collapse" : "Expand"} ({message.steps.length})</span>
              <span className={message.stepsOpen ? "chevron open" : "chevron"}>
                <ChevronIcon />
              </span>
            </button>
            <div className={message.stepsOpen ? "steps open" : "steps"}>
              {message.steps.map((step, index) => (
                <div className="step" key={`${message.id}-step-${index}`}>
                  <span className="step-index">[{index + 1}]</span>
                  {step}
                </div>
              ))}
            </div>
          </>
        )}

        {message.media.length > 0 && (
          <div className="thumb-list">
            {message.media.map((item) =>
              item.src.startsWith("data:video") ? (
                <video className="thumb" src={item.src} muted controls key={item.id} />
              ) : (
                <img className="thumb" src={item.src} alt={item.name} key={item.id} />
              ),
            )}
          </div>
        )}

        {message.filenames.length > 0 && (
          <div className="file-list">
            {message.filenames.map((filename) => (
              <button className="download-chip" type="button" key={filename} onClick={() => onDownload(filename)}>
                <DownloadIcon />
                <span className="chip-name">{filename}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
