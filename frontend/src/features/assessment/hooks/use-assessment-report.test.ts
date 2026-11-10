import { describe, expect, it, vi } from "vitest";

import { parseJobEvent, readJobEvents } from "@/features/assessment/hooks/use-assessment-report";

describe("parseJobEvent", () => {
  it("parses a valid job event object", () => {
    expect(parseJobEvent('{"status":"running","progress":42,"message":"Scoring"}')).toEqual({
      status: "running",
      progress: 42,
      message: "Scoring",
    });
  });

  it("returns null for malformed JSON instead of throwing", () => {
    expect(parseJobEvent("{not json")).toBeNull();
    expect(parseJobEvent("")).toBeNull();
  });

  it("returns null for JSON that is not an object", () => {
    expect(parseJobEvent("null")).toBeNull();
    expect(parseJobEvent("42")).toBeNull();
    expect(parseJobEvent('"done"')).toBeNull();
    expect(parseJobEvent("[1,2]")).toBeNull();
  });
});

function streamOf(chunks: string[], onCancel?: () => void): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let index = 0;
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (index < chunks.length) controller.enqueue(encoder.encode(chunks[index++]));
      // Keep the stream open after the last chunk, like a live server connection.
    },
    cancel() {
      onCancel?.();
    },
  });
}

describe("readJobEvents", () => {
  it("skips a malformed event and keeps delivering the rest", async () => {
    const events: unknown[] = [];
    await readJobEvents(
      streamOf([
        'data: {"status":"running","progress":10}\n\n',
        "data: {half-sent\n\n",
        'data: {"status":"running","progress":60}\n\n',
        'data: {"status":"completed","progress":100}\n\n',
      ]),
      (event) => events.push(event),
    );

    expect(events).toEqual([
      { status: "running", progress: 10 },
      { status: "running", progress: 60 },
      { status: "completed", progress: 100 },
    ]);
  });

  it("handles an event split across chunks", async () => {
    const events: unknown[] = [];
    await readJobEvents(
      streamOf(['data: {"status":"comp', 'leted","progress":100}\n\n']),
      (event) => events.push(event),
    );

    expect(events).toEqual([{ status: "completed", progress: 100 }]);
  });

  it("throws the backend's message on a failed event and releases the connection", async () => {
    const onCancel = vi.fn();
    await expect(
      readJobEvents(
        streamOf(['data: {"status":"failed","error_message":"Model timed out."}\n\n'], onCancel),
        () => undefined,
      ),
    ).rejects.toThrow("Model timed out.");
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("releases the connection once the job completes", async () => {
    const onCancel = vi.fn();
    await readJobEvents(streamOf(['data: {"status":"completed"}\n\n'], onCancel), () => undefined);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
