import type { SessionPayload, SsePayload } from "./types";

export async function createSession(username: string): Promise<SessionPayload> {
  const data = new FormData();
  data.append("username", username);

  const response = await fetch("/api/session/create", {
    method: "POST",
    body: data,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Session creation failed: ${response.status}`);
  }

  return response.json() as Promise<SessionPayload>;
}

export async function streamChat(
  data: FormData,
  onEvent: (event: SsePayload) => void,
): Promise<void> {
  const response = await fetch("/chat", {
    method: "POST",
    body: data,
  });

  if (!response.ok || !response.body) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || "";

    for (const chunk of chunks) {
      const event = parseSseChunk(chunk);
      if (event) onEvent(event);
    }
  }

  if (buffer.trim()) {
    const event = parseSseChunk(buffer);
    if (event) onEvent(event);
  }
}

function parseSseChunk(chunk: string): SsePayload | null {
  const data = chunk
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trim())
    .join("\n");

  if (!data) return null;
  return JSON.parse(data) as SsePayload;
}
