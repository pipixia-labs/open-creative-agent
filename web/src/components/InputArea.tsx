import { useLayoutEffect, useRef, useState } from "react";
import { PaperclipIcon, SendIcon } from "./icons";

type InputAreaProps = {
  disabled: boolean;
  onSend: (prompt: string, files: File[]) => void;
};

export default function InputArea({ disabled, onSend }: InputAreaProps) {
  const [prompt, setPrompt] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [isComposing, setIsComposing] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const canSend = !disabled && (prompt.trim().length > 0 || files.length > 0);

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    const minHeight = 72;
    const maxHeight = 216;
    const nextHeight = Math.max(minHeight, Math.min(textarea.scrollHeight, maxHeight));
    textarea.style.height = `${nextHeight}px`;
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? "auto" : "hidden";
  }, [prompt]);

  const send = () => {
    if (!canSend) return;
    onSend(prompt.trim(), files);
    setPrompt("");
    setFiles([]);
  };

  return (
    <form
      className="input-area"
      onSubmit={(event) => {
        event.preventDefault();
        send();
      }}
    >
      {files.length > 0 && (
        <div className="attachment-preview">
          {files.map((file, index) => (
            <span className="file-chip" key={`${file.name}-${index}`}>
              <span className="chip-name">{file.name}</span>
              <button
                type="button"
                className="remove-file"
                aria-label={`Remove ${file.name}`}
                onClick={() => setFiles((current) => current.filter((_, itemIndex) => itemIndex !== index))}
              >
                x
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="composer-box">
        <label className="visually-hidden" htmlFor="message">
          Prompt
        </label>
        <textarea
          ref={textareaRef}
          id="message"
          className="composer-textarea"
          value={prompt}
          rows={3}
          placeholder="Describe what you want to create or analyze..."
          disabled={disabled}
          onChange={(event) => setPrompt(event.target.value)}
          onCompositionStart={() => setIsComposing(true)}
          onCompositionEnd={() => setIsComposing(false)}
          onKeyDown={(event) => {
            const plainEnter =
              event.key === "Enter" && !event.shiftKey && !event.altKey && !event.ctrlKey && !event.metaKey;
            if (!plainEnter) return;
            const nativeEvent = event.nativeEvent as KeyboardEvent & { isComposing?: boolean; keyCode?: number };
            if (isComposing || nativeEvent.isComposing || nativeEvent.keyCode === 229) return;
            event.preventDefault();
            send();
          }}
        />
        <div className="composer-actions">
          <label className="file-button" htmlFor="attachments" title="Attach files" aria-label="Attach files">
            <PaperclipIcon />
          </label>
          <input
            id="attachments"
            className="visually-hidden"
            type="file"
            multiple
            accept="image/png,image/jpeg,image/bmp,.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.csv,.txt,.md,.zip"
            disabled={disabled}
            onChange={(event) => {
              setFiles((current) => [...current, ...Array.from(event.target.files || [])]);
              event.target.value = "";
            }}
          />
          <button className="send-button" type="submit" title="Send" aria-label="Send" disabled={!canSend}>
            <SendIcon />
          </button>
        </div>
      </div>
    </form>
  );
}
