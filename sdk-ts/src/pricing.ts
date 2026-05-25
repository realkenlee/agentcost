/** USD per 1M tokens [input, output] */
const PRICES: Record<string, [number, number]> = {
  // Anthropic
  "claude-opus-4-7":            [15.0,  75.0],
  "claude-opus-4-5":            [15.0,  75.0],
  "claude-sonnet-4-6":          [3.0,   15.0],
  "claude-sonnet-4-5":          [3.0,   15.0],
  "claude-haiku-4-5":           [0.80,  4.0],
  "claude-3-5-sonnet-20241022": [3.0,   15.0],
  "claude-3-5-haiku-20241022":  [0.80,  4.0],
  // OpenAI
  "gpt-4o":                     [2.50,  10.0],
  "gpt-4o-mini":                [0.15,  0.60],
  "o1":                         [15.0,  60.0],
  "o3":                         [10.0,  40.0],
  "o3-mini":                    [1.10,  4.40],
  // Google
  "gemini-2.0-flash":           [0.10,  0.40],
  "gemini-1.5-pro":             [1.25,  5.0],
  // Groq
  "llama-3.3-70b-versatile":    [0.59,  0.79],
  "llama-3.1-8b-instant":       [0.05,  0.08],
};

const PREFIX_FALLBACKS: [string, [number, number]][] = [
  ["claude-opus",   [15.0, 75.0]],
  ["claude-sonnet", [3.0,  15.0]],
  ["claude-haiku",  [0.80, 4.0]],
  ["gpt-4o-mini",   [0.15, 0.60]],
  ["gpt-4o",        [2.50, 10.0]],
  ["gpt-4",         [10.0, 30.0]],
  ["o1",            [15.0, 60.0]],
  ["o3",            [10.0, 40.0]],
  ["gemini-2",      [0.10, 0.40]],
  ["gemini-1.5",    [1.25, 5.0]],
  ["llama-3.3",     [0.59, 0.79]],
  ["llama",         [0.10, 0.10]],
];

export function costUsd(model: string, inputTokens: number, outputTokens: number): number | null {
  const m = model.toLowerCase().replace(/^[^/]+\//, ""); // strip "anthropic/" prefix
  let price = PRICES[m];
  if (!price) {
    for (const [prefix, p] of PREFIX_FALLBACKS) {
      if (m.startsWith(prefix)) { price = p; break; }
    }
  }
  if (!price) return null;
  return (inputTokens * price[0] + outputTokens * price[1]) / 1_000_000;
}
