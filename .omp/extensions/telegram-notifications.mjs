import { readFileSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { basename, join } from "node:path";

const MAX_MESSAGE_LENGTH = 4096;
const REQUEST_TIMEOUT_MS = 5000;
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
  return `${text.slice(0, MAX_MESSAGE_LENGTH - 32)}\n… [truncated]`;
}

export function isBlockerMessage(value) {
  const text = String(value || "");
  if (
    /^\s*(?:STATUS|COMPLETION STATUS)\s*:\s*(?:BLOCKED|NEEDS_HUMAN_REVIEW)\b/im.test(
      text,
    )
  ) {
    return true;
  }
  return /\b(?:blocker|blocked|cannot continue|needs human review|requires a decision)\b|заблокирован|требуется решение|не могу продолжить/i.test(
    text,
  );
}

export function looksLikeFinalMessage(value) {
  return /^\s*(?:STATUS|COMPLETION STATUS|PR)\s*:/im.test(String(value || ""));
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

function notificationText(kind, text) {
  const project = basename(process.cwd()) || "project";
  const title = kind === "blocker" ? "⛔ OMP blocker" : "✅ OMP завершил работу";
  return `${title}\nПроект: ${project}\n\n${text || "Итоговый текст отсутствует."}`;
}

export default function telegramNotifications(pi) {
  let lastAssistantMessage = "";
  let finalNotificationSent = false;

  const notify = (kind, text) => {
    void sendTelegramMessage(notificationText(kind, text));
  };

  pi.on("agent_start", async () => {
    lastAssistantMessage = "";
    finalNotificationSent = false;
  });

  pi.on("message_end", async (event) => {
    const text = assistantText(event?.message);
    if (!text) return;
    lastAssistantMessage = text;

    if (isBlockerMessage(text)) notify("blocker", text);
    if (looksLikeFinalMessage(text)) {
      notify("completion", text);
      finalNotificationSent = true;
    }
  });

  pi.on("agent_end", async () => {
    if (finalNotificationSent) return;
    notify("completion", lastAssistantMessage);
  });
}
