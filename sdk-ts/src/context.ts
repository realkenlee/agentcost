import { AsyncLocalStorage } from "async_hooks";

const storage = new AsyncLocalStorage<Record<string, string>>();

export function currentLabels(): Record<string, string> {
  return storage.getStore() ?? {};
}

export function withLabels<T>(labels: Record<string, string>, fn: () => T): T {
  const merged = { ...currentLabels(), ...labels };
  return storage.run(merged, fn);
}
