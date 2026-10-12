"use client"

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { MergeDiff } from "@/components/shared/MarkdownField"
import { Button } from "@/components/ui/button"
import { getRunDiff, listRunArtifacts } from "@/features/runs/api"
import { queryKeys } from "@/lib/api/query-keys"

const tabs = ["Diff", "Build & tests", "Screenshots", "Preview"] as const

export function stripAnsi(text: string) {
  return text.replace(/\u001b\[[0-9;]*m/g, "")
}

export function lineDelta(before: string, after: string) {
  const oldLines = new Set(before.split("\n"))
  const newLines = new Set(after.split("\n"))
  let added = 0
  let removed = 0
  for (const line of newLines) if (!oldLines.has(line)) added += 1
  for (const line of oldLines) if (!newLines.has(line)) removed += 1
  return { added, removed }
}

function textFrom(url: string) {
  const marker = "data:text/plain,"
  if (!url.startsWith(marker)) return url
  return stripAnsi(decodeURIComponent(url.slice(marker.length)))
}

export function RunCentre({ id, previewUrl }: { id: string; previewUrl?: string }) {
  const [tab, setTab] = useState<(typeof tabs)[number]>("Diff")
  const [path, setPath] = useState<string | null>(null)
  const [shot, setShot] = useState<string | null>(null)
  const diff = useQuery({ queryKey: queryKeys.runs.diff(id), queryFn: () => getRunDiff(id) })
  const artifacts = useQuery({ queryKey: queryKeys.runs.artifacts(id), queryFn: () => listRunArtifacts(id) })
  const files = diff.data?.files ?? []
  const selected = files.find((file) => file.path === path) ?? files[0]
  const logs = (artifacts.data ?? []).filter((item) => item.kind === "log")
  const shots = (artifacts.data ?? []).filter((item) => item.kind === "screenshot")

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div role="tablist" aria-label="Run output" className="flex gap-1 border-b p-2">
        {tabs.map((name) => (
          <Button key={name} role="tab" aria-selected={tab === name} size="sm" variant={tab === name ? "secondary" : "ghost"} onClick={() => setTab(name)}>
            {name}
          </Button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-3">
        {tab === "Diff" ? (
          files.length === 0 ? (
            <p className="text-sm text-muted-foreground">No files changed</p>
          ) : (
            <div className="flex flex-col gap-3">
              <ul className="flex flex-col gap-1">
                {files.map((file) => {
                  const delta = lineDelta(file.before, file.after)
                  return (
                    <li key={file.path}>
                      <button type="button" className="text-sm underline" onClick={() => setPath(file.path)}>
                        {file.path} +{delta.added} -{delta.removed}
                      </button>
                    </li>
                  )
                })}
              </ul>
              {selected ? <MergeDiff before={selected.before} after={selected.after} /> : null}
            </div>
          )
        ) : null}
        {tab === "Build & tests" ? (
          logs.length === 0 ? (
            <p className="text-sm text-muted-foreground">No logs yet</p>
          ) : (
            <pre tabIndex={0} className="max-h-80 overflow-auto font-mono text-xs">
              {logs.map((log) => textFrom(log.url ?? "")).join("\n")}
            </pre>
          )
        ) : null}
        {tab === "Screenshots" ? (
          shots.length === 0 ? (
            <p className="text-sm text-muted-foreground">No screenshots yet</p>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              {shots.map((item) => (
                <button key={item.id} type="button" className="flex flex-col gap-1 text-left" onClick={() => setShot(item.url ?? null)}>
                  <img src={item.url} alt={item.viewport ?? item.name} className="h-auto w-full rounded border" />
                  <span className="text-xs">{item.viewport}</span>
                </button>
              ))}
            </div>
          )
        ) : null}
        {tab === "Preview" ? (
          previewUrl ? (
            <div className="flex h-full flex-col gap-2">
              <a href={previewUrl} target="_blank" rel="noreferrer" className="text-sm underline">
                Open in new tab
              </a>
              <iframe title="Preview" src={previewUrl} className="min-h-64 w-full flex-1 rounded border" />
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No preview yet</p>
          )
        ) : null}
      </div>
      {shot ? (
        <dialog open className="fixed inset-0 z-50 m-auto max-w-3xl bg-background p-4">
          <img src={shot} alt="Enlarged screenshot" className="h-auto w-full" />
          <Button className="mt-2" variant="outline" onClick={() => setShot(null)}>
            Close
          </Button>
        </dialog>
      ) : null}
    </div>
  )
}
