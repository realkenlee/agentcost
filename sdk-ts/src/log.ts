import fs from "fs";
import os from "os";
import path from "path";

let logPath: string = path.join(os.homedir(), ".agentcost", "events.jsonl");

export function setup(p?: string): void {
  if (p) logPath = p;
  fs.mkdirSync(path.dirname(logPath), { recursive: true });
}

export interface Event {
  ts: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number | null;
  latency_ms?: number;
  [key: string]: unknown;
}

export function record(event: Event): void {
  const line = JSON.stringify(event) + "\n";
  try {
    fs.appendFileSync(logPath, line);
  } catch {
    // non-fatal
  }
}

export function loadEvents(p?: string): Event[] {
  const file = p ?? logPath;
  if (!fs.existsSync(file)) return [];
  return fs.readFileSync(file, "utf8")
    .split("\n")
    .filter(Boolean)
    .flatMap(line => { try { return [JSON.parse(line)]; } catch { return []; } });
}
