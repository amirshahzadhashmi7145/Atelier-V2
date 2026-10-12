import { deflateRawSync } from "node:zlib"
import { describe, expect, it } from "vitest"
import { skillFromEntries, unzip } from "@/features/skills/zip"

function zip(files: { name: string; data: string }[]) {
  const locals: Buffer[] = []
  const centrals: Buffer[] = []
  let offset = 0
  for (const file of files) {
    const name = Buffer.from(file.name)
    const raw = Buffer.from(file.data)
    const compressed = deflateRawSync(raw)
    const local = Buffer.alloc(30)
    local.writeUInt32LE(0x04034b50, 0)
    local.writeUInt16LE(20, 4)
    local.writeUInt16LE(8, 8)
    local.writeUInt32LE(compressed.length, 18)
    local.writeUInt32LE(raw.length, 22)
    local.writeUInt16LE(name.length, 26)
    const chunk = Buffer.concat([local, name, compressed])
    locals.push(chunk)
    const central = Buffer.alloc(46)
    central.writeUInt32LE(0x02014b50, 0)
    central.writeUInt16LE(20, 4)
    central.writeUInt16LE(20, 6)
    central.writeUInt16LE(8, 10)
    central.writeUInt32LE(compressed.length, 20)
    central.writeUInt32LE(raw.length, 24)
    central.writeUInt16LE(name.length, 28)
    central.writeUInt32LE(offset, 42)
    centrals.push(Buffer.concat([central, name]))
    offset += chunk.length
  }
  const centralBuf = Buffer.concat(centrals)
  const eocd = Buffer.alloc(22)
  eocd.writeUInt32LE(0x06054b50, 0)
  eocd.writeUInt16LE(files.length, 8)
  eocd.writeUInt16LE(files.length, 10)
  eocd.writeUInt32LE(centralBuf.length, 12)
  eocd.writeUInt32LE(offset, 16)
  return Buffer.concat([...locals, centralBuf, eocd])
}

describe("zip skill", () => {
  it("unpacks SKILL.md and a sibling file", async () => {
    const archive = zip([
      {
        name: "react/SKILL.md",
        data: "---\nname: react-best-practices\ndescription: Load when writing React UI.\n---\n# Body\n",
      },
      { name: "react/notes.md", data: "extra" },
    ])
    const entries = await unzip(archive.buffer.slice(archive.byteOffset, archive.byteOffset + archive.byteLength))
    expect(skillFromEntries(entries)).toEqual({
      name: "react-best-practices",
      description: "Load when writing React UI.",
      body: "# Body",
      files: [{ name: "notes.md", size: 5 }],
    })
  })

  it("unpacks an entry whose sizes live in a data descriptor", async () => {
    const name = "react/SKILL.md"
    const data = "---\nname: react-best-practices\ndescription: Load when writing React UI.\n---\n# Body\n"
    const nameBuf = Buffer.from(name)
    const raw = Buffer.from(data)
    const compressed = deflateRawSync(raw)
    const local = Buffer.alloc(30)
    local.writeUInt32LE(0x04034b50, 0)
    local.writeUInt16LE(20, 4)
    local.writeUInt16LE(0x0008, 6)
    local.writeUInt16LE(8, 8)
    local.writeUInt16LE(nameBuf.length, 26)
    const descriptor = Buffer.alloc(16)
    descriptor.writeUInt32LE(0x08074b50, 0)
    descriptor.writeUInt32LE(compressed.length, 8)
    descriptor.writeUInt32LE(raw.length, 12)
    const central = Buffer.alloc(46)
    central.writeUInt32LE(0x02014b50, 0)
    central.writeUInt16LE(0x0008, 8)
    central.writeUInt16LE(8, 10)
    central.writeUInt32LE(compressed.length, 20)
    central.writeUInt32LE(raw.length, 24)
    central.writeUInt16LE(nameBuf.length, 28)
    const centralBuf = Buffer.concat([central, nameBuf])
    const offset = 30 + nameBuf.length + compressed.length + descriptor.length
    const eocd = Buffer.alloc(22)
    eocd.writeUInt32LE(0x06054b50, 0)
    eocd.writeUInt16LE(1, 8)
    eocd.writeUInt16LE(1, 10)
    eocd.writeUInt32LE(centralBuf.length, 12)
    eocd.writeUInt32LE(offset, 16)
    const archive = Buffer.concat([local, nameBuf, compressed, descriptor, centralBuf, eocd])
    const entries = await unzip(archive.buffer.slice(archive.byteOffset, archive.byteOffset + archive.byteLength))
    expect(skillFromEntries(entries).name).toBe("react-best-practices")
  })
})
