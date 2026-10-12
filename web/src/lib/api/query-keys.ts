export const queryKeys = {
  agents: ["agents"] as const,
  tools: ["tools"] as const,
  skills: ["skills"] as const,
  runs: (page = 1) => ["runs", page] as const,
}
