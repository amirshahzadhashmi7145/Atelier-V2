export type Bubble = { callId: string; parts: Map<number, string> }

export function placeDelta(bubbles: Bubble[], callId: string, index: number, text: string): Bubble[] {
  const next = bubbles.map((bubble) => ({ callId: bubble.callId, parts: new Map(bubble.parts) }))
  let bubble = next.find((item) => item.callId === callId)
  if (!bubble) {
    bubble = { callId, parts: new Map() }
    next.push(bubble)
  }
  bubble.parts.set(index, text)
  return next
}

export function bubbleText(bubble: Bubble) {
  return [...bubble.parts.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([, text]) => text)
    .join("")
}
