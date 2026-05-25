/**
 * agentcost — token attribution for AI agents (TypeScript/Node.js)
 *
 * Works with: openai, @anthropic-ai/sdk, Vercel AI SDK (ai package)
 *
 * Usage:
 *   import { init, withLabels } from "agentcost";
 *   init();
 *
 *   // existing code unchanged — all LLM calls auto-tracked
 *   const client = new OpenAI();
 *   await client.chat.completions.create({ model: "gpt-4o", messages: [...] });
 *
 *   // optional manual labels
 *   await withLabels({ pr: "1234", team: "platform" }, async () => {
 *     await client.chat.completions.create(...);
 *   });
 */

export { withLabels, currentLabels } from "./context";
export { loadEvents } from "./log";

import { setup } from "./log";
import { getGitContext } from "./git";
import { currentLabels } from "./context";
import { costUsd } from "./pricing";
import { record } from "./log";

let _initialized = false;

export function init(logPath?: string): void {
  if (_initialized) return;
  _initialized = true;

  setup(logPath);

  const patched: string[] = [];
  if (patchOpenAI())     patched.push("openai");
  if (patchAnthropic())  patched.push("@anthropic-ai/sdk");
  if (patchVercelAI())   patched.push("vercel-ai-sdk");

  if (patched.length) {
    console.log(`[agentcost] tracking: ${patched.join(", ")}`);
  } else {
    console.log("[agentcost] no supported LLM client found");
  }
}

function _record(model: string, inputTokens: number, outputTokens: number, latencyMs?: number): void {
  const git = getGitContext();
  const labels = currentLabels();
  record({
    ts:            new Date().toISOString(),
    model,
    input_tokens:  inputTokens,
    output_tokens: outputTokens,
    cost_usd:      costUsd(model, inputTokens, outputTokens),
    latency_ms:    latencyMs,
    ...Object.fromEntries(Object.entries(labels).map(([k, v]) => [`label_${k}`, v])),
    ...Object.fromEntries(Object.entries(git).map(([k, v]) => [`git_${k}`, v])),
  });
}

// ── OpenAI ────────────────────────────────────────────────────────────────────

function patchOpenAI(): boolean {
  try {
    const openai = require("openai");
    const Completions = openai.OpenAI?.Chat?.Completions
      ?? openai.default?.Chat?.Completions;
    if (!Completions) return false;

    const orig = Completions.prototype.create;
    Completions.prototype.create = async function (this: unknown, ...args: unknown[]) {
      const t0 = Date.now();
      const response = await orig.apply(this, args);
      const ms = Date.now() - t0;
      try {
        const u = (response as any).usage;
        if (u) _record((response as any).model, u.prompt_tokens, u.completion_tokens, ms);
      } catch { /* */ }
      return response;
    };
    return true;
  } catch {
    return false;
  }
}

// ── Anthropic ─────────────────────────────────────────────────────────────────

function patchAnthropic(): boolean {
  try {
    const anthropic = require("@anthropic-ai/sdk");
    const Messages = anthropic.Anthropic?.Messages ?? anthropic.default?.Messages;
    if (!Messages) return false;

    const orig = Messages.prototype.create;
    Messages.prototype.create = async function (this: unknown, ...args: unknown[]) {
      const t0 = Date.now();
      const response = await orig.apply(this, args);
      const ms = Date.now() - t0;
      try {
        const u = (response as any).usage;
        if (u) _record((response as any).model, u.input_tokens, u.output_tokens, ms);
      } catch { /* */ }
      return response;
    };
    return true;
  } catch {
    return false;
  }
}

// ── Vercel AI SDK ─────────────────────────────────────────────────────────────
// Wraps generateText / streamText / generateObject via telemetry middleware

function patchVercelAI(): boolean {
  try {
    const ai = require("ai");
    if (!ai.generateText) return false;

    const wrap = (fn: Function) => async (...args: unknown[]) => {
      const t0 = Date.now();
      const result = await fn(...args);
      const ms = Date.now() - t0;
      try {
        const usage = (result as any).usage;
        const model = ((args[0] as any)?.model?.modelId) ?? "unknown";
        if (usage) _record(model, usage.promptTokens, usage.completionTokens, ms);
      } catch { /* */ }
      return result;
    };

    if (ai.generateText)  ai.generateText  = wrap(ai.generateText);
    if (ai.streamText)    ai.streamText    = wrap(ai.streamText);
    if (ai.generateObject) ai.generateObject = wrap(ai.generateObject);
    return true;
  } catch {
    return false;
  }
}
