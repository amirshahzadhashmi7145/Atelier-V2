"use client"

import { useState } from "react"
import { z } from "zod"
import { MarkdownField } from "@/components/shared/MarkdownField"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"

const slug = z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/, "Use a lowercase slug")

export type SkillDraft = {
  name: string
  description: string
  body: string
  files: { name: string; size: number }[]
  versions: { version: number; createdAt: string }[]
  origin: string
}

export function SkillEditor({
  initial,
  agents,
  pending,
  onSave,
}: {
  initial: SkillDraft
  agents: { id: string; name: string }[]
  pending?: boolean
  onSave: (draft: SkillDraft) => void
}) {
  const [draft, setDraft] = useState(initial)
  const [nameError, setNameError] = useState<string | null>(null)
  const patch = (partial: Partial<SkillDraft>) => setDraft((current) => ({ ...current, ...partial }))

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>{draft.name || "New skill"}</CardTitle>
          <CardDescription>Origin {draft.origin || "studio"}</CardDescription>
        </CardHeader>
        <CardContent>
          <FieldGroup>
            <Field data-invalid={nameError ? true : undefined}>
              <FieldLabel htmlFor="skill-name">Name</FieldLabel>
              <Input
                id="skill-name"
                value={draft.name}
                aria-invalid={Boolean(nameError)}
                onChange={(event) => patch({ name: event.target.value })}
              />
              <FieldError>{nameError}</FieldError>
            </Field>
            <Field>
              <FieldLabel htmlFor="skill-description">Description</FieldLabel>
              <p className="text-sm text-muted-foreground">say when to load it</p>
              <Input
                id="skill-description"
                value={draft.description}
                onChange={(event) => patch({ description: event.target.value })}
              />
              <p className="text-sm text-muted-foreground">{draft.description.length} characters</p>
            </Field>
          </FieldGroup>
        </CardContent>
      </Card>
      <MarkdownField
        id="skill-body"
        label="Body"
        hint="Markdown the agent reads after load_skill."
        value={draft.body}
        onChange={(body) => patch({ body })}
      />
      <Field>
        <FieldLabel htmlFor="skill-files">Files</FieldLabel>
        <Input
          id="skill-files"
          type="file"
          multiple
          onChange={(event) => {
            const picked = [...(event.target.files ?? [])].map((file) => ({ name: file.name, size: file.size }))
            patch({ files: [...draft.files, ...picked] })
          }}
        />
        <ul className="flex flex-col gap-1 text-sm">
          {draft.files.length === 0 ? <li className="text-muted-foreground">No files.</li> : null}
          {draft.files.map((file) => (
            <li key={file.name}>
              {file.name} · {file.size} bytes
            </li>
          ))}
        </ul>
      </Field>
      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-medium">Versions</h2>
        {draft.versions.length === 0 ? <p className="text-sm text-muted-foreground">Not saved yet.</p> : null}
        <ul className="flex flex-col gap-1 text-sm">
          {draft.versions.map((version) => (
            <li key={version.version}>
              Version {version.version} · {version.createdAt}
            </li>
          ))}
        </ul>
      </section>
      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-medium">Attached to</h2>
        {agents.length === 0 ? <p className="text-sm text-muted-foreground">No agents use this skill.</p> : null}
        <ul className="flex flex-col gap-1 text-sm">
          {agents.map((agent) => (
            <li key={agent.id}>{agent.name}</li>
          ))}
        </ul>
      </section>
      <Button
        disabled={pending}
        onClick={() => {
          const parsed = slug.safeParse(draft.name)
          if (!parsed.success) {
            setNameError(parsed.error.issues[0]?.message ?? "Use a lowercase slug")
            return
          }
          setNameError(null)
          onSave(draft)
        }}
      >
        {pending ? "Saving…" : "Save"}
      </Button>
    </div>
  )
}
