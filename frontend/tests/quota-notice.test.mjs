import assert from "node:assert/strict";
import { test } from "node:test";

import { readChatStream, UsageLimitNotice } from "../src/lib/chat-stream.ts";

test("HTTP 429 is a usage notice, with its friendly server message preserved", async () => {
  const response = new Response(
    JSON.stringify({ detail: "稍等一会儿，刚才的提问有点密集。" }),
    { status: 429, headers: { "content-type": "application/json" } },
  );
  await assert.rejects(
    readChatStream(response, () => {}),
    (error) => error instanceof UsageLimitNotice &&
      error.message === "稍等一会儿，刚才的提问有点密集。",
  );
});

test("HTTP 502 stays a real error, not a rate-limit notice", async () => {
  const response = new Response(
    JSON.stringify({ detail: "AI 生成暂时失败，请稍后再试" }),
    { status: 502, headers: { "content-type": "application/json" } },
  );
  await assert.rejects(
    readChatStream(response, () => {}),
    (error) => error instanceof Error &&
      !(error instanceof UsageLimitNotice) &&
      error.message.includes("AI 生成暂时失败"),
  );
});
