"use client"

import { useEffect, useRef } from "react"

export function MarkdownField({
  id,
  label,
  hint,
  value,
  onChange,
}: {
  id: string
  label: string
  hint: string
  value: string
  onChange: (value: string) => void
}) {
  const host = useRef<HTMLDivElement>(null)
  const onChangeRef = useRef(onChange)
  const initial = useRef(value)

  useEffect(() => {
    onChangeRef.current = onChange
  })

  useEffect(() => {
    const parent = host.current
    if (!parent) return
    let view: { destroy: () => void } | undefined
    let cancelled = false
    void (async () => {
      const [{ EditorView, keymap }, { EditorState }, { markdown }, { defaultKeymap, history, historyKeymap }] =
        await Promise.all([
          import("@codemirror/view"),
          import("@codemirror/state"),
          import("@codemirror/lang-markdown"),
          import("@codemirror/commands"),
        ])
      if (cancelled || !parent) return
      view = new EditorView({
        parent,
        state: EditorState.create({
          doc: initial.current,
          extensions: [
            keymap.of([...defaultKeymap, ...historyKeymap]),
            history(),
            markdown(),
            EditorView.contentAttributes.of({ "aria-label": label, id }),
            EditorView.updateListener.of((update) => {
              if (update.docChanged) onChangeRef.current(update.state.doc.toString())
            }),
            EditorView.theme({
              "&": { border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", fontSize: "13px" },
              ".cm-scroller": { minHeight: "6rem" },
              ".cm-content": { padding: "8px 0" },
            }),
          ],
        }),
      })
    })()
    return () => {
      cancelled = true
      view?.destroy()
    }
  }, [id, label])

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      <p className="text-sm text-muted-foreground">{hint}</p>
      <div ref={host} />
    </div>
  )
}

export function MergeDiff({ before, after }: { before: string; after: string }) {
  const host = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const parent = host.current
    if (!parent) return
    let view: { destroy: () => void } | undefined
    let cancelled = false
    void (async () => {
      const [{ MergeView }, { EditorView }] = await Promise.all([
        import("@codemirror/merge"),
        import("@codemirror/view"),
      ])
      if (cancelled || !parent) return
      view = new MergeView({
        parent,
        a: {
          doc: before,
          extensions: [
            EditorView.editable.of(false),
            EditorView.contentAttributes.of({ "aria-label": "Before" }),
            EditorView.theme({ ".cm-scroller": { overflow: "visible" } }),
          ],
        },
        b: {
          doc: after,
          extensions: [
            EditorView.editable.of(false),
            EditorView.contentAttributes.of({ "aria-label": "After" }),
            EditorView.theme({ ".cm-scroller": { overflow: "visible" } }),
          ],
        },
      })
    })()
    return () => {
      cancelled = true
      view?.destroy()
    }
  }, [before, after])
  // role="group" so the aria-label is permitted even before CodeMirror mounts
  // content into this host (ARIA prohibits aria-label on a bare div).
  return <div ref={host} role="group" aria-label="Version diff" />
}
