/**
 * memex for pi: deterministic memory recall and transcript capture.
 *
 * Layer 2 of the memex integration model — hooks, not model cooperation:
 * - before_agent_start (first turn): injects repo-level recall context
 *   via `memex hook session-start` (branch, last commit as query hints).
 * - before_agent_start (later turns): injects prompt-relevant memories
 *   via `memex hook prompt`.
 * - session_shutdown: ingests the pi session file via `memex hook
 *   transcript`, creating the episode node and transcript provenance.
 *
 * Everything is best-effort: if the memex CLI is missing or slow, the
 * extension stays silent and never disturbs the session.
 */
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const run = promisify(execFile);

const MEMEX_BIN = process.env.MEMEX_BIN ?? "memex";
const TOP_K = process.env.MEMEX_TOP_K ?? "5";
const DISABLED = process.env.MEMEX_DISABLE === "1";
const WRITE_GUIDANCE =
  "When the user states a durable fact, preference, or rule, or asks to memorize one, " +
  "use memex write. Choose --scope project for workspace architecture, conventions, " +
  "and decisions; choose --scope global for facts intended across projects. " +
  "If unclear, choose project. Check the returned file path.";

function injection(content: string) {
  return {
    message: { customType: "memex-memory", content, display: false },
  };
}

export default function (pi: ExtensionAPI) {
  if (DISABLED) return;

  let firstTurn = true;

  pi.on("before_agent_start", async (event, _ctx) => {
    try {
      if (firstTurn) {
        firstTurn = false;
        const { stdout } = await run(MEMEX_BIN, ["hook", "session-start", "--top-k", TOP_K], {
          timeout: 15_000,
        });
        const text = stdout.trim();
        return injection(text ? `${WRITE_GUIDANCE}\n\n${text}` : WRITE_GUIDANCE);
      }
      const prompt = typeof event.prompt === "string" ? event.prompt.trim() : "";
      if (!prompt) return;
      const { stdout } = await run(
        MEMEX_BIN,
        ["hook", "prompt", "--top-k", TOP_K, "--prompt", prompt],
        { timeout: 15_000 },
      );
      const text = stdout.trim();
      if (text) return injection(text);
    } catch {
      // memex unavailable: stay silent.
    }
  });

  pi.on("session_shutdown", async (_event, ctx) => {
    try {
      const file = ctx.sessionManager?.getSessionFile?.();
      if (!file) return;
      await run(MEMEX_BIN, ["hook", "transcript", "--harness", "pi", "--path", String(file)], {
        timeout: 60_000,
      });
    } catch {
      // capture is best-effort; never block shutdown
    }
  });
}
