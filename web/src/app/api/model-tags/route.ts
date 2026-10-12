import { readFile, writeFile } from "node:fs/promises"
import { join } from "node:path"
import { MODEL_TAGS, type ModelTag, type TagRecord } from "@/lib/models/tags"

const file = join(process.cwd(), "data", "model-tags.json")

async function readTags(): Promise<Record<string, TagRecord>> {
  try {
    return JSON.parse(await readFile(file, "utf8")) as Record<string, TagRecord>
  } catch {
    return {}
  }
}

export async function GET() {
  return Response.json(await readTags())
}

export async function PUT(request: Request) {
  const body = (await request.json()) as { name?: string; tags?: string[]; note?: string }
  if (!body.name) return Response.json({ error: "name is required" }, { status: 400 })
  const tags = (body.tags ?? []).filter((tag): tag is ModelTag => (MODEL_TAGS as readonly string[]).includes(tag))
  const current = await readTags()
  current[body.name] = { tags, note: body.note ?? "", heuristic: false }
  await writeFile(file, `${JSON.stringify(current, null, 2)}\n`)
  return Response.json(current[body.name])
}
