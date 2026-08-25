/**
 * Incremental parser for Server-Sent Events read from a fetch ReadableStream.
 *
 * A network chunk is not a message. One read can carry several events, one
 * event can be split across several reads, and a split can land in the middle
 * of a JSON payload or between the two newlines that terminate a frame. The
 * previous reader decoded each chunk on its own and looked for lines starting
 * with "data: ", so any event unlucky enough to straddle a chunk boundary was
 * dropped — which showed up as detection runs whose progress froze, or whose
 * final result never arrived.
 *
 * This buffers whatever has not yet formed a complete frame and hands it back
 * to the next read. CRLF and LF are both accepted.
 */

export interface SSEEvent<T = unknown> {
  /** The event name, "message" when the frame did not name one. */
  event: string;
  /** Parsed JSON payload, or null when the data was not JSON. */
  data: T | null;
  /** The raw data text, useful for diagnostics when parsing failed. */
  raw: string;
}

/** Splits a byte stream into complete SSE frames across chunk boundaries. */
export class SSEParser {
  private buffer = "";

  /**
   * Feed one decoded chunk. Returns every event that is now complete; the
   * incomplete tail is retained for the next call.
   */
  push(chunk: string): SSEEvent[] {
    this.buffer += chunk;
    const events: SSEEvent[] = [];

    // A frame ends at a blank line: \n\n, \r\n\r\n, or the mixed forms.
    const separator = /\r?\n\r?\n/;
    let match = separator.exec(this.buffer);
    while (match) {
      const frame = this.buffer.slice(0, match.index);
      this.buffer = this.buffer.slice(match.index + match[0].length);
      const parsed = parseFrame(frame);
      if (parsed) events.push(parsed);
      match = separator.exec(this.buffer);
    }

    return events;
  }

  /**
   * Flush a final frame that the server sent without a trailing blank line.
   * Call once after the reader reports done.
   */
  flush(): SSEEvent[] {
    const remainder = this.buffer;
    this.buffer = "";
    if (!remainder.trim()) return [];
    const parsed = parseFrame(remainder);
    return parsed ? [parsed] : [];
  }
}

/** Parse one complete frame's field lines. */
export function parseFrame(frame: string): SSEEvent | null {
  let event = "";
  const dataLines: string[] = [];

  for (const rawLine of frame.split(/\r?\n/)) {
    const line = rawLine.replace(/\r$/, "");
    if (!line || line.startsWith(":")) continue; // blank or comment

    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    // One optional space after the colon is part of the framing, not the value.
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);

    if (field === "event") event = value;
    else if (field === "data") dataLines.push(value);
    // id and retry are accepted and ignored.
  }

  if (!dataLines.length) return null;

  const raw = dataLines.join("\n");
  let data: unknown = null;
  try {
    data = JSON.parse(raw);
  } catch {
    data = null;
  }

  return { event: event || "message", data, raw };
}

/**
 * Read an SSE response to completion, calling back per event.
 *
 * Handles the reader lifecycle, buffering, and the final flush, so callers only
 * deal with events. The reader is always released.
 */
export async function readSSEStream(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: SSEEvent) => void,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  const parser = new SSEParser();

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      // stream: true keeps a multi-byte character split across chunks intact.
      for (const event of parser.push(decoder.decode(value, { stream: true }))) {
        onEvent(event);
      }
    }
    for (const event of parser.push(decoder.decode())) onEvent(event);
    for (const event of parser.flush()) onEvent(event);
  } finally {
    reader.releaseLock();
  }
}
