import assert from "node:assert/strict";
import { chmod, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  isBlockerMessage,
  looksLikeFinalMessage,
  parseEnvFile,
  readTelegramSettings,
  redactNotificationText,
  sendTelegramMessage,
} from "../../.omp/extensions/telegram-notifications.mjs";

test("parses notification settings without changing token text", () => {
  assert.deepEqual(
    parseEnvFile(
      "# comment\nOMP_TELEGRAM_BOT_TOKEN=123456:short-test-token\nOMP_TELEGRAM_CHAT_ID=974111221\n",
    ),
    {
      OMP_TELEGRAM_BOT_TOKEN: "123456:short-test-token",
      OMP_TELEGRAM_CHAT_ID: "974111221",
    },
  );
});

test("rejects a notification file that is readable by other users", async () => {
  const directory = await mkdtemp(join(tmpdir(), "medcore-telegram-"));
  const path = join(directory, "omp-telegram.env");
  try {
    await writeFile(path, "OMP_TELEGRAM_BOT_TOKEN=test\nOMP_TELEGRAM_CHAT_ID=1\n");
    await chmod(path, 0o644);
    assert.equal(readTelegramSettings(path), null);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("redacts credential-shaped text and detects explicit workflow states", () => {
  const fakeGithubToken = `gho_${"x".repeat(24)}`;
  const message = `STATUS: BLOCKED\nsecret=${fakeGithubToken}`;
  const redacted = redactNotificationText(message);
  assert.equal(redacted.includes("gho_"), false);
  assert.equal(isBlockerMessage(message), true);
  assert.equal(isBlockerMessage("STATUS: DONE\nPR: https://github.com/example/pr/1"), false);
  assert.equal(looksLikeFinalMessage("STATUS: DONE\nPR: none"), true);
});

test("sends a bounded plain-text Telegram message", async () => {
  let request;
  const ok = await sendTelegramMessage(
    "STATUS: DONE\nPR: none",
    { token: "123456:short-test-token", chatId: "974111221" },
    async (url, options) => {
      request = { url, options };
      return { ok: true };
    },
  );

  assert.equal(ok, true);
  assert.match(request.url, /api\.telegram\.org\/bot/);
  assert.equal(JSON.parse(request.options.body).chat_id, "974111221");
  assert.equal(JSON.parse(request.options.body).text, "STATUS: DONE\nPR: none");
});

test("setup-file fixture remains readable only by this user", async () => {
  const directory = await mkdtemp(join(tmpdir(), "medcore-telegram-"));
  const path = join(directory, "omp-telegram.env");
  try {
    await writeFile(path, "OMP_TELEGRAM_BOT_TOKEN=test\nOMP_TELEGRAM_CHAT_ID=1\n");
    await chmod(path, 0o600);
    assert.deepEqual(readTelegramSettings(path), {
      token: "test",
      chatId: "1",
    });
    assert.match(await readFile(path, "utf8"), /OMP_TELEGRAM_CHAT_ID=1/);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
