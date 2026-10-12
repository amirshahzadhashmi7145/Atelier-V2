import { parseSkillMarkdown } from "@/features/skills/frontmatter"

export type ZipEntry = { name: string; text: string }

async function inflateRaw(data: Uint8Array) {
  const stream = new DecompressionStream("deflate-raw")
  const writer = stream.writable.getWriter()
  await writer.write(new Uint8Array(data))
  await writer.close()
  return new Uint8Array(await new Response(stream.readable).arrayBuffer())
}

export async function unzip(buffer: ArrayBuffer): Promise<ZipEntry[]> {
  const bytes = new Uint8Array(buffer)
  const view = new DataView(buffer)
  let eocd = -1
  for (let i = bytes.length - 22; i >= 0; i -= 1) {
    if (view.getUint32(i, true) === 0x06054b50) {
      eocd = i
      break
    }
  }
  if (eocd < 0) throw new Error("Not a zip archive")
  const count = view.getUint16(eocd + 10, true)
  let cursor = view.getUint32(eocd + 16, true)
  const entries: ZipEntry[] = []
  const decoder = new TextDecoder()
  for (let n = 0; n < count; n += 1) {
    if (view.getUint32(cursor, true) !== 0x02014b50) throw new Error("Bad zip directory")
    const method = view.getUint16(cursor + 10, true)
    const compressedSize = view.getUint32(cursor + 20, true)
    const nameLength = view.getUint16(cursor + 28, true)
    const extraLength = view.getUint16(cursor + 30, true)
    const commentLength = view.getUint16(cursor + 32, true)
    const localOffset = view.getUint32(cursor + 42, true)
    const name = decoder.decode(bytes.subarray(cursor + 46, cursor + 46 + nameLength))
    cursor += 46 + nameLength + extraLength + commentLength
    if (name.endsWith("/")) continue
    const localNameLength = view.getUint16(localOffset + 26, true)
    const localExtra = view.getUint16(localOffset + 28, true)
    const dataStart = localOffset + 30 + localNameLength + localExtra
    const compressed = bytes.subarray(dataStart, dataStart + compressedSize)
    const raw = method === 0 ? compressed : method === 8 ? await inflateRaw(compressed) : null
    if (!raw) throw new Error(`Unsupported zip method ${method}`)
    entries.push({ name, text: decoder.decode(raw) })
  }
  return entries
}

export function skillFromEntries(entries: ZipEntry[]) {
  const skillFile = entries.find((entry) => entry.name === "SKILL.md" || entry.name.endsWith("/SKILL.md"))
  if (!skillFile) throw new Error("Zip has no SKILL.md")
  const parsed = parseSkillMarkdown(skillFile.text)
  const root = skillFile.name.slice(0, -"SKILL.md".length)
  const files = entries
    .filter((entry) => entry.name !== skillFile.name && entry.name.startsWith(root))
    .map((entry) => ({
      name: entry.name.slice(root.length),
      size: new TextEncoder().encode(entry.text).length,
    }))
  return { ...parsed, files }
}
