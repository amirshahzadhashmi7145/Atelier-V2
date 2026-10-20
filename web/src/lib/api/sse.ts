export type SseFrame = { id: number; event: string; data: string }

export function parseSseChunk(buffer: string): { frames: SseFrame[]; rest: string } {
  const parts = buffer.split("\n\n")
  const rest = parts.pop() ?? ""
  const frames = parts.filter((part) => part.trim().length > 0).map(parseFrame)
  return { frames, rest }
}

function parseFrame(raw: string): SseFrame {
  let id = 0
  let event = "message"
  const data: string[] = []
  for (const line of raw.split("\n")) {
    if (line.startsWith("id:")) id = Number(line.slice(3).trim())
    else if (line.startsWith("event:")) event = line.slice(6).trim()
    else if (line.startsWith("data:")) data.push(line.slice(5).trim())
  }
  return { id, event, data: data.join("\n") }
}

export async function readEventStream(
  url: string,
  after: number,
  onFrame: (frame: SseFrame) => void,
  signal?: AbortSignal,
) {
  const joiner = url.includes("?") ? "&" : "?"
  const response = await fetch(`${url}${joiner}after=${after}`, {
    headers: { Accept: "text/event-stream" },
    signal,
  })
  if (!response.ok || !response.body) {
    throw new Error(`Event stream failed (${response.status})`)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  const seen = new Set<string>()
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parsed = parseSseChunk(buffer)
    buffer = parsed.rest
    for (const frame of parsed.frames) {
      if (!frame.data) continue
      let key = String(frame.id)
      let seq = frame.id
      try {
        const payload = JSON.parse(frame.data) as { id?: string; seq?: number; type?: string }
        if (payload.id) key = payload.id
        if (typeof payload.seq === "number") seq = payload.seq
        if (payload.type !== "MODEL_DELTA" && seq > 0 && seq <= after) continue
      } catch {
        if (seq > 0 && seq <= after) continue
      }
      if (seen.has(key)) continue
      seen.add(key)
      onFrame(frame)
    }
  }
}
