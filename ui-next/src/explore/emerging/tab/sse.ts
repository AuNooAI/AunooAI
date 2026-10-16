/*
 * Server-sent events read from a fetch stream, copied from ui/src/utils/sseParser.ts. A network chunk
 * isn't a message: one read can carry several events and one event can be split across reads, so
 * whatever hasn't formed a complete frame waits for the next read.
 */

export interface SSEEvent {
  /** The event name, "message" when the frame didn't name one */
  event: string;
  /** Parsed JSON payload, or null when the data wasn't JSON */
  data: unknown;
}

function parseFrame(frame: string): SSEEvent | null {
  let event = '';
  const dataLines: string[] = [];
  for (const rawLine of frame.split(/\r?\n/)) {
    const line = rawLine.replace(/\r$/, '');
    if (!line || line.startsWith(':')) continue;
    const colon = line.indexOf(':');
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? '' : line.slice(colon + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    if (field === 'event') event = value;
    else if (field === 'data') dataLines.push(value);
  }
  if (!dataLines.length) return null;
  let data: unknown = null;
  try {
    data = JSON.parse(dataLines.join('\n'));
  } catch {
    data = null;
  }
  return { event: event || 'message', data };
}

export async function readSSEStream(body: ReadableStream<Uint8Array>, onEvent: (e: SSEEvent) => void): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  const drain = () => {
    const sep = /\r?\n\r?\n/;
    let m = sep.exec(buffer);
    while (m) {
      const frame = buffer.slice(0, m.index);
      buffer = buffer.slice(m.index + m[0].length);
      const parsed = parseFrame(frame);
      if (parsed) onEvent(parsed);
      m = sep.exec(buffer);
    }
  };
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      drain();
    }
    buffer += decoder.decode();
    drain();
    if (buffer.trim()) {
      const parsed = parseFrame(buffer);
      if (parsed) onEvent(parsed);
    }
  } finally {
    reader.releaseLock();
  }
}
