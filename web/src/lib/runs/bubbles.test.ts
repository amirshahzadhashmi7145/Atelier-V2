import { describe, expect, it } from "vitest"
import { bubbleText, placeDelta } from "@/lib/runs/bubbles"

describe("model bubbles", () => {
  it("keeps two calls apart and orders each by index", () => {
    let bubbles = placeDelta([], "a", 2, "bubble.")
    bubbles = placeDelta(bubbles, "b", 1, "Second ")
    bubbles = placeDelta(bubbles, "a", 1, "First ")
    bubbles = placeDelta(bubbles, "b", 2, "bubble.")
    bubbles = placeDelta(bubbles, "a", 1, "First ")
    expect(bubbles.map(bubbleText)).toEqual(["First bubble.", "Second bubble."])
  })
})
