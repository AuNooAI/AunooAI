/**
 * SSE parsing across arbitrary network chunk boundaries.
 *
 * A chunk is not a message. The reader this replaced decoded each chunk on its
 * own and scanned for lines beginning with "data: ", so any event split across
 * two reads was silently dropped — a detection run whose progress froze, or
 * whose final payload never arrived.
 *
 * Run with: npm test  (from ui/)
 */

import test from "node:test";
import assert from "node:assert/strict";

import { SSEParser, parseFrame, readSSEStream } from "../src/utils/sseParser";

function frame(event: string, payload: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`;
}

test("parses a single complete frame", () => {
  const parser = new SSEParser();
  const events = parser.push(frame("progress", { progress: 25 }));

  assert.equal(events.length, 1);
  assert.equal(events[0].event, "progress");
  assert.deepEqual(events[0].data, { progress: 25 });
});

test("parses several frames arriving in one chunk", () => {
  const parser = new SSEParser();
  const chunk =
    frame("progress", { progress: 10 }) +
    frame("progress", { progress: 20 }) +
    frame("complete", { status: "completed" });

  const events = parser.push(chunk);

  assert.deepEqual(events.map((e) => e.event), ["progress", "progress", "complete"]);
});

test("keeps an event split across two chunks", () => {
  const parser = new SSEParser();
  const whole = frame("complete", { status: "completed", total: 3 });
  const cut = Math.floor(whole.length / 2);

  assert.deepEqual(parser.push(whole.slice(0, cut)), []);
  const events = parser.push(whole.slice(cut));

  assert.equal(events.length, 1);
  assert.deepEqual(events[0].data, { status: "completed", total: 3 });
});

test("keeps an event split inside its JSON payload", () => {
  const parser = new SSEParser();
  parser.push('event: progress\ndata: {"message": "half of a sent');
  const events = parser.push('ence", "progress": 42}\n\n');

  assert.equal(events.length, 1);
  assert.deepEqual(events[0].data, { message: "half of a sentence", progress: 42 });
});

test("keeps an event split inside the terminating blank line", () => {
  const parser = new SSEParser();
  assert.deepEqual(parser.push('event: progress\ndata: {"progress": 5}\n'), []);
  const events = parser.push("\nevent: complete\ndata: {}\n\n");

  assert.deepEqual(events.map((e) => e.event), ["progress", "complete"]);
});

test("survives one byte at a time", () => {
  const parser = new SSEParser();
  const stream =
    frame("progress", { progress: 1, message: "unicode: ✓ é" }) +
    frame("complete", { status: "completed" });

  const events = [];
  for (const char of stream) events.push(...parser.push(char));

  assert.deepEqual(events.map((e) => e.event), ["progress", "complete"]);
  assert.equal((events[0].data as { message: string }).message, "unicode: ✓ é");
});

test("accepts CRLF line endings", () => {
  const parser = new SSEParser();
  const events = parser.push('event: progress\r\ndata: {"progress": 7}\r\n\r\n');

  assert.equal(events.length, 1);
  assert.deepEqual(events[0].data, { progress: 7 });
});

test("handles a mix of CRLF and LF in the same stream", () => {
  const parser = new SSEParser();
  const events = parser.push(
    'event: a\r\ndata: {"n": 1}\r\n\r\nevent: b\ndata: {"n": 2}\n\n',
  );

  assert.deepEqual(events.map((e) => e.event), ["a", "b"]);
});

test("surfaces an error frame with its code", () => {
  const parser = new SSEParser();
  const events = parser.push(
    frame("error", {
      status: "failed",
      code: "embedding_unavailable",
      message: "DeBERTa encoder unreachable",
    }),
  );

  assert.equal(events[0].event, "error");
  assert.equal((events[0].data as { code: string }).code, "embedding_unavailable");
});

test("flush emits a final frame the server left unterminated", () => {
  const parser = new SSEParser();
  assert.deepEqual(parser.push('event: complete\ndata: {"status": "completed"}'), []);

  const events = parser.flush();

  assert.equal(events.length, 1);
  assert.equal(events[0].event, "complete");
});

test("flush on an empty buffer emits nothing", () => {
  const parser = new SSEParser();
  parser.push(frame("progress", {}));
  assert.deepEqual(parser.flush(), []);
});

test("a frame without a data line is ignored", () => {
  const parser = new SSEParser();
  assert.deepEqual(parser.push(": keep-alive comment\n\n"), []);
  assert.deepEqual(parser.push("event: progress\n\n"), []);
});

test("unparseable data is reported rather than thrown", () => {
  const parsed = parseFrame("event: progress\ndata: not json");

  assert.ok(parsed);
  assert.equal(parsed!.data, null);
  assert.equal(parsed!.raw, "not json");
});

test("an unnamed frame defaults to the message event", () => {
  const parsed = parseFrame('data: {"progress": 3}');
  assert.equal(parsed!.event, "message");
});

test("multi-line data fields are joined", () => {
  const parsed = parseFrame('data: {"a":\ndata: 1}');
  assert.deepEqual(parsed!.data, { a: 1 });
});

test("readSSEStream delivers every event across ragged chunks", async () => {
  const payload =
    frame("progress", { progress: 10 }) +
    frame("progress", { progress: 55 }) +
    frame("complete", { status: "completed", total_emerging_topics: 2 });

  // Chop the payload at deliberately awkward offsets.
  const cuts = [3, 30, 31, 90, 140];
  const encoder = new TextEncoder();
  const pieces: Uint8Array[] = [];
  let previous = 0;
  for (const cut of [...cuts, payload.length]) {
    if (cut <= previous) continue;
    pieces.push(encoder.encode(payload.slice(previous, cut)));
    previous = cut;
  }

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const piece of pieces) controller.enqueue(piece);
      controller.close();
    },
  });

  const seen: string[] = [];
  await readSSEStream(stream, (event) => seen.push(event.event));

  assert.deepEqual(seen, ["progress", "progress", "complete"]);
});

test("readSSEStream flushes a stream that ends without a blank line", async () => {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode('event: complete\ndata: {"status": "completed"}'));
      controller.close();
    },
  });

  const seen: string[] = [];
  await readSSEStream(stream, (event) => seen.push(event.event));

  assert.deepEqual(seen, ["complete"]);
});
