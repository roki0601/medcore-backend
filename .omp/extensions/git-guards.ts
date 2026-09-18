type ToolEvent = {
  toolName?: string;
  input?: Record<string, unknown>;
};

type SpawnResult = {
  exitCode: number;
};

function runStagedSafetyCheck(): boolean {
  const runtime = globalThis as typeof globalThis & {
    Bun?: {
      spawnSync: (args: string[], options?: { cwd?: string }) => SpawnResult;
    };
  };

  if (!runtime.Bun) {
    return false;
  }

  const projectRoot = process.cwd();
  const result = runtime.Bun.spawnSync(
    ["bash", `${projectRoot}/scripts/ai/check-git-safety.sh`],
    { cwd: projectRoot },
  );
  return result.exitCode === 0;
}

function blockedReason(command: string): string | undefined {
  const normalized = command.replace(/\s+/g, " ").trim();

  if (/\bgit\s+push\b/i.test(normalized)) {
    if (/(--force(?:-with-lease)?|\s-f(?:\s|$))/i.test(normalized)) {
      return "force-push is blocked by the project Git policy";
    }
    if (/(^|\s)(main|master)(:|\s|$)/i.test(normalized)) {
      return "push to main/master is blocked by the project Git policy";
    }
    if (
      !/(^|\s)(?:feature|codex|bugfix|fix|chore|docs|test|refactor)\/[A-Za-z0-9._/-]+(?:\s|$)/i.test(
        normalized,
      )
    ) {
      return "push requires an explicit feature-style branch name";
    }
  }

  if (/\bgit\s+merge\b|\bgh\s+pr\s+merge\b/i.test(normalized)) {
    return "merge/auto-merge is blocked; merge only through an explicit human-reviewed flow";
  }

  if (
    /\bgit\s+reset\s+[^;|&]*--hard\b|\bgit\s+clean\b|\bgit\s+rebase\b|\bgit\s+branch\s+[^;|&]*-D\b/i.test(
      normalized,
    )
  ) {
    return "destructive/history-rewriting Git operation is blocked";
  }

  if (/\bgit\s+(?:checkout\s+--|restore\b)/i.test(normalized)) {
    return "working-tree discard operation is blocked";
  }

  if (/\bgit\s+commit\b/i.test(normalized)) {
    if (/(--no-verify|\s-n(?:\s|$))/i.test(normalized)) {
      return "--no-verify commits are blocked";
    }
    if (!runStagedSafetyCheck()) {
      return "commit blocked: staged-secret safety check failed";
    }
  }

  return undefined;
}

export default function gitGuards(pi: {
  on: (event: "tool_call", handler: (event: ToolEvent) => unknown) => void;
}) {
  pi.on("tool_call", async (event) => {
    if (event.toolName !== "bash") {
      return undefined;
    }

    const command = String(event.input?.command ?? "");
    const reason = blockedReason(command);
    if (reason) {
      return {
        block: true,
        reason: `MedCore project Git guard: ${reason}`,
      };
    }

    return undefined;
  });
}
