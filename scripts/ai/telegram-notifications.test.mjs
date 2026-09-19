import assert from "node:assert/strict";
import { chmod, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  classifyManagerMessage,
  escapeMarkdownV2,
  formatNotificationReport,
  isBlockerMessage,
  looksLikeFinalMessage,
  notificationText,
  parseSubagentCompletion,
  parseEnvFile,
  readTelegramSettings,
  redactNotificationText,
  sendTelegramMessage,
  default as telegramNotifications,
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

test("ignores narrative blocker mentions in a final report", () => {
  const report = `Feature delivered.

## Blocker notification
No hard blocker required Telegram escalation — reviewer findings were resolved.`;

  assert.equal(isBlockerMessage(report), false);
  assert.equal(classifyManagerMessage(report), null);
  assert.equal(classifyManagerMessage("STATUS: BLOCKED\nNeed owner decision"), "blocker");
  assert.equal(classifyManagerMessage("STATUS: DONE\nPR: none"), "completion");
});

test("sends a bounded MarkdownV2 Telegram message", async () => {
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
  assert.equal(JSON.parse(request.options.body).parse_mode, "MarkdownV2");
  assert.equal(JSON.parse(request.options.body).text, "STATUS: DONE\nPR: none");
});

test("escapes MarkdownV2 control characters in dynamic values", () => {
  assert.equal(
    escapeMarkdownV2("feature_004 [media] (local) #1.2"),
    "feature\\_004 \\[media\\] \\(local\\) \\#1\\.2",
  );
});

test("converts limited Markdown to safe Telegram MarkdownV2", () => {
  const report = formatNotificationReport(`
# Проверка 002-content-catalog-access
Кириллица, _underscore_, - тире, точка., [media].
**Важно: 002-content-catalog-access**
Путь: \`/home/roki/dev/medcore/[media]/002-content-catalog-access.py\`
- первый пункт
* второй пункт
+ третий пункт
`);

  assert.equal(
    report,
    "*Проверка 002\\-content\\-catalog\\-access*\n" +
      "Кириллица, \\_underscore\\_, \\- тире, точка\\., \\[media\\]\\.\n" +
      "*Важно: 002\\-content\\-catalog\\-access*\n" +
      "Путь: `/home/roki/dev/medcore/[media]/002-content-catalog-access.py`\n" +
      "• первый пункт\n" +
      "• второй пункт\n" +
      "• третий пункт",
  );
  assert.equal(
    formatNotificationReport("Код: `C:\\tmp\\file`"),
    "Код: `C:\\\\tmp\\\\file`",
  );
});

test("escapes unsupported and unclosed Markdown without leaking delimiters", () => {
  assert.equal(
    formatNotificationReport(
      "Обычный *текст* _текст_ [media] (локально) - = ! # + | { } ~ > `незакрытый",
    ),
    "Обычный \\*текст\\* \\_текст\\_ \\[media\\] \\(локально\\) \\- \\= \\! \\# \\+ \\| \\{ \\} \\~ \\> \\`незакрытый",
  );
});

test("formats the manager report as a compact MarkdownV2 message", () => {
  const text = notificationText("completion", "STATUS: DONE\nPR: none", {
    name: "manager",
    role: "manager",
    flow: "main",
  });

  assert.match(text, /\*Агент:\* `manager`/);
  assert.match(text, /\*Роль:\* `manager`/);
  assert.match(text, /\*Проект:\* `medcore-backend`/);
  assert.match(text, /\*Итог:\*/);
  assert.match(text, /STATUS: DONE/);
  assert.doesNotMatch(text, /Итоговый текст отсутствует/);
});

test("extracts a completed subagent identity and concise conclusion", () => {
  const result = parseSubagentCompletion(`
    ## Completed (1)
    <task-result id="WatchdogEscalation002" agent="watchdog" status="completed">
      {"verdict":"BLOCKED","summary":"Spec 002 still has unresolved contract questions."}
    </task-result>
  `);

  assert.deepEqual(result, {
    id: "WatchdogEscalation002",
    agent: "watchdog",
    status: "completed",
    verdict: "BLOCKED",
    summary: "Spec 002 still has unresolved contract questions.",
  });
});

test("ignores ordinary tool output without a completed subagent result", () => {
  assert.equal(parseSubagentCompletion("reading specs/002-content-catalog-access"), null);
});

function notificationHarness() {
  const handlers = new Map();
  const sent = [];
  telegramNotifications(
    {
      on(name, handler) {
        handlers.set(name, handler);
      },
    },
    {
      send: async (text) => {
        sent.push(text);
        return true;
      },
    },
  );
  return { handlers, sent };
}

test("does not notify on intermediate agent_end and reports an unconfirmed empty session once", async () => {
  const { handlers, sent } = notificationHarness();

  assert.equal(handlers.has("agent_end"), false);
  assert.equal(sent.length, 0);

  await handlers.get("session_shutdown")({});
  await handlers.get("session_shutdown")({});
  assert.equal(sent.length, 1);
  assert.match(sent[0], /итог не подтверждён/i);
  assert.doesNotMatch(sent[0], /Итоговый текст отсутствует/);
});

test("sends one final report at session shutdown without duplicating agent turns", async () => {
  const { handlers, sent } = notificationHarness();

  await handlers.get("message_end")({
    message: {
      role: "assistant",
      stopReason: "stop",
      content: "Все проверки пройдены.\nИтоговый отчёт сформирован.",
    },
  });
  await handlers.get("session_shutdown")({});

  assert.equal(sent.length, 1);
  assert.match(sent[0], /\*✅ OMP завершил работу\*/);
  assert.match(sent[0], /Все проверки пройдены/);
});

test("does not spam successful subagent completions and deduplicates blockers", async () => {
  const { handlers, sent } = notificationHarness();

  const successful =
    '<task-result id="Impl004" agent="implementer" status="completed">' +
    '{"verdict":"READY","summary":"Зона готова."}</task-result>';
  await handlers.get("tool_execution_end")({ result: successful });
  assert.equal(sent.length, 0);

  const blocked =
    '<task-result id="Review004" agent="senior-reviewer" status="completed">' +
    '{"verdict":"BLOCKED","summary":"Нужна правка контракта."}</task-result>';
  await handlers.get("tool_execution_end")({ result: blocked });
  await handlers.get("tool_execution_end")({ result: blocked });
  assert.equal(sent.length, 1);
  assert.match(sent[0], /Нужна правка контракта/);
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
