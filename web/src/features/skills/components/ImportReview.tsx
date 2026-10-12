"use client"

import { Button } from "@/components/ui/button"

export function ImportReview({
  name,
  description,
  body,
  files,
  diff,
  pending,
  onConfirm,
}: {
  name: string
  description: string
  body: string
  files: { name: string }[]
  diff: { path: string; before: string; after: string }[]
  pending?: boolean
  onConfirm: () => void
}) {
  return (
    <div className="flex flex-col gap-3">
      <h2 className="text-sm font-medium">Review {name}</h2>
      <p className="text-sm text-muted-foreground">{description}</p>
      <pre tabIndex={0} className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg border p-3 text-sm">
        {body}
      </pre>
      {files.length > 0 ? (
        <ul className="text-sm">
          {files.map((file) => (
            <li key={file.name}>{file.name}</li>
          ))}
        </ul>
      ) : null}
      {diff.map((row) => (
        <div key={row.path} className="flex flex-col gap-1">
          <p className="text-sm font-medium">{row.path}</p>
          {row.before === row.after ? <p className="text-sm text-muted-foreground">No text changes</p> : null}
          <pre className="whitespace-pre-wrap text-sm">{row.before}</pre>
          <pre className="whitespace-pre-wrap text-sm">{row.after}</pre>
        </div>
      ))}
      <Button disabled={pending} onClick={onConfirm}>
        {pending ? "Saving…" : "Confirm"}
      </Button>
    </div>
  )
}
