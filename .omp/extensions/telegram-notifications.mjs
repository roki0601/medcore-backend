import { readFileSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { basename, join } from "node:path";

const MAX_MESSAGE_LENGTH = 4096;
const MINI_REPORT_LENGTH = 2200;
const REQUEST_TIMEOUT_MS = 5000;
const MARKDOWN_V2_SPECIAL_CHARACTERS = new Set(
  "\\_*[]()~`>#+-=|{}.!".split(""),
);
const DEFAULT_ENV_FILE = join(
  process.env.XDG_CONFIG_HOME || join(homedir(), ".config"),
  "medcore",
  "omp-telegram.env",
);

function stripQuotes(value) {
  const trimmed = value.trim();
  if (
    trimmed.length >= 2 &&
    ((trimmed.startsWith("\"") && trimmed.endsWith("\"")) ||
      (trimmed.startsWith("'") && trimmed.endsWith("'")))
  ) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

export function parseEnvFile(contents) {
  const values = {};
  for (const rawLine of contents.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const match = line.match(/^([A-Z][A-Z0-9_]*)=(.*)$/);
    if (match) values[match[1]] = stripQuotes(match[2]);
  }
  return values;
}

export function readTelegramSettings(
  envFile = process.env.OMP_TELEGRAM_ENV_FILE || DEFAULT_ENV_FILE,
) {
  try {
    const mode = statSync(envFile).mode & 0o777;
    if (mode & 0o077) return null;

    const values = parseEnvFile(readFileSync(envFile, "utf8"));
    const token = values.OMP_TELEGRAM_BOT_TOKEN;
    const chatId = values.OMP_TELEGRAM_CHAT_ID;
    if (!token || !chatId) return null;
    return { token, chatId };
  } catch {
    return null;
  }
}

export function redactNotificationText(value) {
  return String(value || "")
    .replace(/\b\d{8,12}:[A-Za-z0-9_-]{30,}\b/g, "[REDACTED_SECRET]")
    .replace(
      /\b(?:eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}|gh[opurs]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|sk-[A-Za-z0-9_-]{20,})\b/gi,
      "[REDACTED_SECRET]",
    )
    .replace(
      /\b(authorization|token|secret|password|cookie)\s*[:=]\s*[^\s,;]+/gi,
      "$1=[REDACTED_SECRET]",
    )
    .trim();
}

function limitMessage(value) {
  const text = redactNotificationText(value);
  if (text.length <= MAX_MESSAGE_LENGTH) return text;
  return `${text.slice(0, MAX_MESSAGE_LENGTH - 42)}\n…\\[сообщение обрезано\\]`;
}

export function escapeMarkdownV2(value) {
  return [...String(value ?? "")]
    .map((character) =>
      MARKDOWN_V2_SPECIAL_CHARACTERS.has(character)
        ? `\\${character}`
        : character,
    )
    .join("");
}

function escapeMarkdownV2Code(value) {
  return String(value ?? "")
    .replace(/\\/g, "\\\\")
    .replace(/`/g, "\\`")
    .replace(/\s+/g, " ")
    .trim();
}

function inlineCode(value) {
  return `\`${escapeMarkdownV2Code(value)}\``;
}

function isEscapedAt(value, index) {
  let backslashes = 0;
  for (let cursor = index - 1; cursor >= 0 && value[cursor] === "\\"; cursor -= 1) {
    backslashes += 1;
  }
  return backslashes % 2 === 1;
}

function findUnescaped(value, delimiter, start) {
  let index = value.indexOf(delimiter, start);
  while (index !== -1) {
    if (!isEscapedAt(value, index)) return index;
    index = value.indexOf(delimiter, index + delimiter.length);
  }
  return -1;
}

function findBoldClosing(value, start) {
  let index = start;
  while (index < value.length) {
    if (value[index] === "`" && !isEscapedAt(value, index)) {
      const codeClosing = findUnescaped(value, "`", index + 1);
      if (codeClosing === -1) return -1;
      index = codeClosing + 1;
      continue;
    }
    if (
      value.startsWith("**", index) &&
      !isEscapedAt(value, index)
    ) {
      return index;
    }
    index += 1;
  }
  return -1;
}

function formatInlineMarkdown(value, { allowBold = true } = {}) {
  const text = String(value ?? "");
  let output = "";
  let plainStart = 0;
  let index = 0;

  const appendPlainText = (end) => {
    if (end > plainStart) {
      output += escapeMarkdownV2(text.slice(plainStart, end));
    }
  };

  while (index < text.length) {
    if (
      allowBold &&
      text.startsWith("**", index) &&
      !isEscapedAt(text, index)
    ) {
      const closing = findBoldClosing(text, index + 2);
      if (closing > index + 2) {
        appendPlainText(index);
        output += `*${formatInlineMarkdown(text.slice(index + 2, closing), {
          allowBold: false,
        })}*`;
        index = closing + 2;
        plainStart = index;
        continue;
      }
    }

    if (text[index] === "`" && !isEscapedAt(text, index)) {
      const closing = findUnescaped(text, "`", index + 1);
      if (closing > index + 1) {
        appendPlainText(index);
        output += inlineCode(text.slice(index + 1, closing));
        index = closing + 1;
        plainStart = index;
        continue;
      }
    }

    index += 1;
  }

  appendPlainText(text.length);
  return output;
}

function formatReportLine(value) {
  const line = String(value || "").trim();
  if (!line) return "";

  const heading = line.match(/^#{1,6}\s+(.+)$/);
  if (heading) {
    return `*${formatInlineMarkdown(heading[1], { allowBold: false })}*`;
  }

  const bullet = line.match(/^[-*+]\s+(.+)$/);
  if (bullet) return `• ${formatInlineMarkdown(bullet[1])}`;

  return formatInlineMarkdown(line);
}

export function formatNotificationReport(value) {
  const text = redactNotificationText(value);
  if (!text) return "";

  const lines = [];
  for (const rawLine of text.split(/\r?\n/)) {
    const formatted = formatReportLine(rawLine);
    if (formatted || lines.at(-1)) lines.push(formatted);
  }
  return lines.join("\n").trim();
}

function miniReport(value) {
  const text = formatNotificationReport(value);
  if (text.length <= MINI_REPORT_LENGTH) return text;
  const marker = "\n…\\[обрезано\\]";
  const limit = MINI_REPORT_LENGTH - marker.length;
  const cut = text.slice(0, limit);
  const lastLine = cut.lastIndexOf("\n");
  const safeCut = lastLine > limit * 0.75 ? cut.slice(0, lastLine) : cut;
  return `${safeCut.trimEnd()}${marker}`;
}

function decodeJsonString(value) {
  try {
    return JSON.parse(`"${value}"`);
  } catch {
    return value.replace(/\\"/g, '"').replace(/\\n/g, "\n");
  }
}

function taskResultAttribute(text, name) {
  const match = text.match(
    new RegExp(`<task-result\\b[^>]*\\b${name}=["']([^"']+)["']`, "i"),
  );
  return match?.[1] || "";
}

export function parseSubagentCompletion(value) {
  const text = String(value || "");
  if (!/<task-result\b/i.test(text)) return null;

  const id = taskResultAttribute(text, "id");
  const agent = taskResultAttribute(text, "agent");
  const status = taskResultAttribute(text, "status");
  if (!id || !agent || !status) return null;

  const verdict = text.match(
    /["']?verdict["']?\s*:\s*["'](READY|BLOCKED|NEEDS_HUMAN_REVIEW|RESOLVED)["']/i,
  )?.[1]?.toUpperCase() || "";
  const summaryMatch = text.match(
    /["']summary["']\s*:\s*"((?:\\.|[^"\\])*)"/i,
  );
  const summary = summaryMatch
    ? decodeJsonString(summaryMatch[1])
    : miniReport(text.replace(/<[^>]+>/g, "")).trim();

  return { id, agent, status, verdict, summary };
}

export function isBlockerMessage(value) {
  const text = String(value || "");
  return (
    /^\s*(?:STATUS|COMPLETION STATUS|СТАТУС)\s*:\s*(?:BLOCKED|NEEDS_HUMAN_REVIEW|ЗАБЛОКИРОВАН|ТРЕБУЕТСЯ РЕШЕНИЕ)\b/im.test(
      text,
    ) ||
    /^\s*(?:BLOCKER|БЛОКЕР)\s*:\s*(?!NONE\b|NO\b|НЕТ\b).+/im.test(text)
  );
}

export function looksLikeFinalMessage(value) {
  return /^\s*(?:STATUS|COMPLETION STATUS|PR)\s*:/im.test(String(value || ""));
}

export function classifyManagerMessage(value) {
  if (isBlockerMessage(value)) return "blocker";
  if (looksLikeFinalMessage(value)) return "completion";
  return null;
}

export async function sendTelegramMessage(
  text,
  settings = readTelegramSettings(),
  fetchImpl = globalThis.fetch,
) {
  if (!settings || typeof fetchImpl !== "function") return false;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetchImpl(
      `https://api.telegram.org/bot${encodeURIComponent(settings.token)}/sendMessage`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          chat_id: settings.chatId,
          text: limitMessage(text),
          parse_mode: "MarkdownV2",
          link_preview_options: { is_disabled: true },
        }),
        signal: controller.signal,
      },
    );
    return response?.ok !== false;
  } catch {
    // Notifications must never fail or interrupt the OMP run.
    return false;
  } finally {
    clearTimeout(timeout);
  }
}

function assistantText(message) {
  if (!message || message.role !== "assistant") return "";
  if (typeof message.content === "string") return message.content;
  if (!Array.isArray(message.content)) return "";
  return message.content
    .filter((part) => part && part.type === "text")
    .map((part) => part.text || "")
    .join("");
}

export function notificationText(kind, text, identity = {}) {
  const project = basename(process.cwd()) || "project";
  const title =
    kind === "blocker"
      ? "⛔ OMP: блокер"
      : kind === "warning"
        ? "⚠️ OMP: итог не подтверждён"
        : "✅ OMP завершил работу";
  const name = identity.name || process.env.OMP_AGENT_NAME || "manager";
  const role = identity.role || process.env.OMP_AGENT_ROLE || "manager";
  const flow = identity.flow || "main";
  const section =
    kind === "blocker" ? "Проблема" : kind === "warning" ? "Состояние" : "Итог";
  const body = miniReport(text) || "Детали не переданы\\.";
  return [
    `*${escapeMarkdownV2(title)}*`,
    "",
    "━━━━━━━━━━━━━━",
    `*Проект:* ${inlineCode(project)}`,
    `*Агент:* ${inlineCode(name)}`,
    `*Роль:* ${inlineCode(role)}`,
    `*Поток:* ${inlineCode(flow)}`,
    "",
    `*${escapeMarkdownV2(section)}:*`,
    body,
    "",
    "━━━━━━━━━━━━━━",
  ].join("\n");
}

function extractEventText(value, depth = 0) {
  if (depth > 3 || value == null) return "";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    return value.map((item) => extractEventText(item, depth + 1)).join("\n");
  }
  if (typeof value !== "object") return "";

  return ["result", "output", "text", "content", "response", "resultText"]
    .map((key) => extractEventText(value[key], depth + 1))
    .filter(Boolean)
    .join("\n");
}

export default function telegramNotifications(pi, options = {}) {
  let lastAssistantMessage = "";
  let lastAssistantStopReason = "";
  let managerCompletionNotificationSent = false;
  let managerBlockerNotificationSent = false;
  const notifiedSubagents = new Set();
  const send =
    options.send ||
    ((text) => sendTelegramMessage(text, options.settings));

  const notify = async (kind, text, identity) => {
    try {
      return await send(notificationText(kind, text, identity));
    } catch {
      return false;
    }
  };

  pi.on("session_start", async () => {
    lastAssistantMessage = "";
    lastAssistantStopReason = "";
    managerCompletionNotificationSent = false;
    managerBlockerNotificationSent = false;
    notifiedSubagents.clear();
  });

  pi.on("message_end", async (event) => {
    const text = assistantText(event?.message);
    if (!text) return;
    lastAssistantMessage = text;
    lastAssistantStopReason = event?.message?.stopReason || "";

    const kind = classifyManagerMessage(text);
    if (!kind) return;

    if (kind === "blocker") {
      if (managerBlockerNotificationSent) return;
      managerBlockerNotificationSent = true;
      await notify(kind, text, { name: "manager", role: "manager", flow: "main" });
      return;
    }

    if (managerCompletionNotificationSent) return;
    managerCompletionNotificationSent = true;
    await notify(kind, text, { name: "manager", role: "manager", flow: "main" });
  });

  pi.on("tool_execution_end", async (event) => {
    const result = parseSubagentCompletion(extractEventText(event));
    if (!result || notifiedSubagents.has(result.id)) return;
    notifiedSubagents.add(result.id);

    const isActionable =
      result.verdict === "BLOCKED" ||
      result.verdict === "NEEDS_HUMAN_REVIEW" ||
      isBlockerMessage(result.summary);
    if (!isActionable) return;

    const report = [
      result.verdict ? `Вердикт: ${result.verdict}` : "",
      result.summary ? `Вывод: ${result.summary}` : "",
    ]
      .filter(Boolean)
      .join("\n");
    await notify("blocker", report, {
      name: result.id,
      role: result.agent,
      flow: "subagent",
    });
  });

  pi.on("session_shutdown", async () => {
    if (managerCompletionNotificationSent) return;

    managerCompletionNotificationSent = true;
    if (lastAssistantMessage.trim() && lastAssistantStopReason === "stop") {
      await notify("completion", lastAssistantMessage, {
        name: "manager",
        role: "manager",
        flow: "main",
      });
      return;
    }

    const details = lastAssistantMessage.trim()
      ? "Результат не подтверждён: менеджер не выдал явный финальный статус.\nПоследнее сообщение:\n" +
        lastAssistantMessage
      : "Результат не подтверждён: менеджер не прислал итоговый текст.";
    await notify("warning", details, {
      name: "manager",
      role: "manager",
      flow: "main",
    });
  });
}
