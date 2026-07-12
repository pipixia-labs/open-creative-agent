export type MessageRole = "user" | "assistant";

export type MessageStatus = "idle" | "running" | "done" | "error";

export type CanvasMedia = {
  id: string;
  src: string;
  name: string;
};

export type AttachedFile = {
  name: string;
};

export type ChatMessage = {
  id: string;
  role: MessageRole;
  content: string;
  status: MessageStatus;
  steps: string[];
  stepsOpen: boolean;
  files: AttachedFile[];
  media: CanvasMedia[];
  filenames: string[];
};

export type SessionPayload = {
  user_id: string;
  session_id: string;
  message: string;
};

export type SsePayload = {
  type?: "step" | "final" | "error";
  content?: unknown;
};

export type FinalPayload = {
  text?: string;
  final_output_text?: string | null;
  image?: string[];
  filenames?: string[];
};
