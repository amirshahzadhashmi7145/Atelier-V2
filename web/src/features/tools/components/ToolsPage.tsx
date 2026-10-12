"use client"

import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { PageHeader } from "@/components/shared/PageHeader"
import { QueryBody } from "@/components/shared/QueryBody"
import { Button } from "@/components/ui/button"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import {
  createDataSource,
  createTool,
  discoverMcp,
  importApiSpec,
  listDataSources,
  listToolAgents,
  listTools,
  refreshDataSource,
  updateTool,
} from "@/features/tools/api"
import { mcpToolsToCreate, operationsToTools } from "@/features/tools/import-map"
import { validateSchemaText } from "@/features/tools/schema-doc"
import { ToolCard } from "@/features/tools/components/ToolCard"
import { queryKeys } from "@/lib/api/query-keys"
import type { components } from "@/lib/api/generated/types"

type Tool = components["schemas"]["ToolDefinition"]
type Tab = "builtin" | "client" | "mcp" | "api" | "data"

const TABS: [Tab, string][] = [
  ["builtin", "Built-in"],
  ["client", "Client-side"],
  ["mcp", "MCP"],
  ["api", "APIs"],
  ["data", "Data"],
]

const BUILTIN_CONFIG: Record<string, { label: string; key: string; hint: string }> = {
  files: { label: "Allowed paths", key: "allowedPaths", hint: "One path per line" },
  package_install: { label: "Registry allow-list", key: "registries", hint: "One registry per line" },
  headless_browser: { label: "Viewports", key: "viewports", hint: "One viewport per line" },
  search_data: { label: "Allowed domains", key: "allowedDomains", hint: "One domain per line" },
}

export function ToolsPage() {
  const queryClient = useQueryClient()
  const tools = useQuery({ queryKey: queryKeys.tools, queryFn: listTools })
  const agents = useQuery({ queryKey: queryKeys.agents, queryFn: listToolAgents })
  const sources = useQuery({ queryKey: queryKeys.dataSources, queryFn: listDataSources })
  const [tab, setTab] = useState<Tab>("builtin")
  const [configure, setConfigure] = useState<Tool | null>(null)
  const [sheet, setSheet] = useState<"client" | "mcp" | "api" | "data" | null>(null)
  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.tools })
    await queryClient.invalidateQueries({ queryKey: queryKeys.dataSources })
  }
  const fail = (error: unknown) => toast.error(error instanceof Error ? error.message : "Request failed")
  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => updateTool(id, { enabled }),
    onSuccess: async () => invalidate(),
    onError: fail,
  })

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Tools" description="Built-in tools, and the ones you add. Control tools stay hidden." />
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Tool kinds">
        {TABS.map(([id, label]) => (
          <Button
            key={id}
            role="tab"
            aria-selected={tab === id}
            variant={tab === id ? "default" : "outline"}
            onClick={() => setTab(id)}
          >
            {label}
          </Button>
        ))}
      </div>
      {tab === "client" ? <Button onClick={() => setSheet("client")}>Add tool</Button> : null}
      {tab === "mcp" ? <Button onClick={() => setSheet("mcp")}>Add server</Button> : null}
      {tab === "api" ? <Button onClick={() => setSheet("api")}>Import spec</Button> : null}
      {tab === "data" ? <Button onClick={() => setSheet("data")}>Add source</Button> : null}
      {tab === "data" ? (
        <QueryBody query={sources} emptyTitle="No data sources" emptyDescription="Add a source to expose it as search_data.">
          {(rows) => (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left">
                  {["Name", "Kind", "Ref", "Refresh", "Last pulled", "Pages changed", ""].map((heading) => (
                    <th key={heading} className="px-2 py-2 font-medium">
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((source) => (
                  <tr key={source.id} className="border-b">
                    <td className="px-2 py-2">{source.name}</td>
                    <td className="px-2 py-2">{source.kind}</td>
                    <td className="px-2 py-2">{source.ref}</td>
                    <td className="px-2 py-2">{source.refreshPolicy}</td>
                    <td className="px-2 py-2">{source.lastPulledAt ?? "never"}</td>
                    <td className="px-2 py-2">{source.pagesChanged ?? "—"}</td>
                    <td className="px-2 py-2">
                      <RefreshButton id={source.id} onDone={invalidate} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </QueryBody>
      ) : (
        <QueryBody query={tools} emptyTitle="No tools yet" emptyDescription="Built-in tools are part of the runtime.">
          {(items) => {
            const shown = items.filter((tool) => tool.kind === tab)
            if (shown.length === 0) return <p className="text-sm text-muted-foreground">Nothing on this tab yet.</p>
            return (
              <ul className="flex flex-col gap-3">
                {shown.map((tool) => (
                  <li key={tool.id}>
                    <ToolCard
                      tool={tool}
                      usedBy={(agents.data ?? []).filter((agent) => agent.toolIds.includes(tool.id)).length}
                      pending={toggle.isPending}
                      onEnabled={(enabled) => toggle.mutate({ id: tool.id, enabled })}
                      onConfigure={() => setConfigure(tool)}
                    />
                  </li>
                ))}
              </ul>
            )
          }}
        </QueryBody>
      )}
      <ConfigureSheet tool={configure} onClose={() => setConfigure(null)} onSaved={invalidate} />
      <AddSheets open={sheet} onClose={() => setSheet(null)} onSaved={invalidate} />
    </div>
  )
}

function RefreshButton({ id, onDone }: { id: string; onDone: () => Promise<void> }) {
  const refresh = useMutation({
    mutationFn: () => refreshDataSource(id),
    onSuccess: async () => {
      toast.success("Source refreshed")
      await onDone()
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Refresh failed"),
  })
  return (
    <Button variant="outline" size="sm" disabled={refresh.isPending} onClick={() => refresh.mutate()}>
      {refresh.isPending ? "Refreshing…" : "Refresh"}
    </Button>
  )
}

function ConfigureSheet({
  tool,
  onClose,
  onSaved,
}: {
  tool: Tool | null
  onClose: () => void
  onSaved: () => Promise<void>
}) {
  const spec = tool ? BUILTIN_CONFIG[tool.id] : undefined
  const incoming = spec && Array.isArray(tool?.config[spec.key]) ? (tool.config[spec.key] as string[]).join("\n") : ""
  const [text, setText] = useState(incoming)
  const [seen, setSeen] = useState(tool?.id ?? "")
  if ((tool?.id ?? "") !== seen) {
    setSeen(tool?.id ?? "")
    setText(incoming)
  }
  const save = useMutation({
    mutationFn: () => {
      if (!tool || !spec) throw new Error("Nothing to configure")
      const lines = text.split("\n").map((line) => line.trim()).filter(Boolean)
      return updateTool(tool.id, { config: { ...tool.config, [spec.key]: lines } })
    },
    onSuccess: async () => {
      toast.success("Tool updated")
      await onSaved()
      onClose()
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not update the tool"),
  })
  return (
    <Sheet open={Boolean(tool)} onOpenChange={(open) => !open && onClose()}>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>Configure {tool?.name}</SheetTitle>
        </SheetHeader>
        <div className="flex flex-col gap-3 px-4 pb-4">
          {spec ? (
            <>
              <Field>
                <FieldLabel htmlFor="tool-config">{spec.label}</FieldLabel>
                <p className="text-sm text-muted-foreground">{spec.hint}</p>
                <textarea
                  id="tool-config"
                  className="min-h-24 rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm"
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                />
              </Field>
              <Button disabled={save.isPending} onClick={() => save.mutate()}>
                {save.isPending ? "Saving…" : "Save"}
              </Button>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">Nothing to configure.</p>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}

function AddSheets({
  open,
  onClose,
  onSaved,
}: {
  open: "client" | "mcp" | "api" | "data" | null
  onClose: () => void
  onSaved: () => Promise<void>
}) {
  return (
    <Sheet open={Boolean(open)} onOpenChange={(next) => !next && onClose()}>
      <SheetContent className="overflow-auto">
        <SheetHeader>
          <SheetTitle>
            {open === "client" ? "Add tool" : open === "mcp" ? "Add server" : open === "api" ? "Import spec" : "Add source"}
          </SheetTitle>
        </SheetHeader>
        <div className="px-4 pb-4">
          {open === "client" ? <ClientForm onClose={onClose} onSaved={onSaved} /> : null}
          {open === "mcp" ? <McpForm onClose={onClose} onSaved={onSaved} /> : null}
          {open === "api" ? <ApiForm onClose={onClose} onSaved={onSaved} /> : null}
          {open === "data" ? <DataForm onClose={onClose} onSaved={onSaved} /> : null}
        </div>
      </SheetContent>
    </Sheet>
  )
}

function ClientForm({ onClose, onSaved }: { onClose: () => void; onSaved: () => Promise<void> }) {
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [handlerKey, setHandlerKey] = useState("")
  const [schemaText, setSchemaText] = useState('{\n  "type": "object",\n  "properties": {}\n}')
  const schemaError = validateSchemaText(schemaText)
  const save = useMutation({
    mutationFn: () => {
      if (schemaError) throw new Error(schemaError)
      return createTool({
        kind: "client",
        name,
        description,
        schema: JSON.parse(schemaText) as { [key: string]: unknown },
        permission: "read",
        config: { handlerKey },
        source: "client",
        enabled: true,
      })
    },
    onSuccess: async () => {
      toast.success("Tool added")
      await onSaved()
      onClose()
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not add the tool"),
  })
  return (
    <FieldGroup>
      <Field>
        <FieldLabel htmlFor="client-name">Name</FieldLabel>
        <Input id="client-name" value={name} onChange={(event) => setName(event.target.value)} />
      </Field>
      <Field>
        <FieldLabel htmlFor="client-description">Description</FieldLabel>
        <Input id="client-description" value={description} onChange={(event) => setDescription(event.target.value)} />
      </Field>
      <Field>
        <FieldLabel htmlFor="client-schema">JSON Schema</FieldLabel>
        <textarea
          id="client-schema"
          className="min-h-28 rounded-lg border border-input bg-transparent px-2.5 py-2 font-mono text-sm"
          value={schemaText}
          onChange={(event) => setSchemaText(event.target.value)}
        />
        {schemaError ? <p className="text-sm text-destructive">{schemaError}</p> : null}
      </Field>
      <Field>
        <FieldLabel htmlFor="handler-key">Handler key</FieldLabel>
        <Input id="handler-key" value={handlerKey} onChange={(event) => setHandlerKey(event.target.value)} />
      </Field>
      <Button disabled={save.isPending || Boolean(schemaError) || !name || !description || !handlerKey} onClick={() => save.mutate()}>
        {save.isPending ? "Adding…" : "Add tool"}
      </Button>
    </FieldGroup>
  )
}

function McpForm({ onClose, onSaved }: { onClose: () => void; onSaved: () => Promise<void> }) {
  const [name, setName] = useState("")
  const [serverUrl, setServerUrl] = useState("")
  const [auth, setAuth] = useState<"none" | "header" | "oauth">("none")
  const [picked, setPicked] = useState<string[]>([])
  const discover = useMutation({
    mutationFn: () => discoverMcp({ name, serverUrl, auth }),
    onError: (error) => toast.error(error instanceof Error ? error.message : "Discover failed"),
  })
  const confirm = useMutation({
    mutationFn: async () => {
      const selected = (discover.data?.tools ?? []).filter((tool) => picked.includes(tool.name))
      const creates = mcpToolsToCreate({ name, url: serverUrl, auth }, selected)
      for (const body of creates) await createTool(body)
    },
    onSuccess: async () => {
      toast.success("MCP tools added")
      await onSaved()
      onClose()
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not add the tools"),
  })
  return (
    <FieldGroup>
      <Field>
        <FieldLabel htmlFor="mcp-name">Name</FieldLabel>
        <Input id="mcp-name" value={name} onChange={(event) => setName(event.target.value)} />
      </Field>
      <Field>
        <FieldLabel htmlFor="mcp-url">URL</FieldLabel>
        <Input id="mcp-url" value={serverUrl} onChange={(event) => setServerUrl(event.target.value)} />
      </Field>
      <Field>
        <FieldLabel htmlFor="mcp-auth">Auth</FieldLabel>
        <select
          id="mcp-auth"
          className="h-8 rounded-lg border border-input bg-transparent px-2.5 text-sm"
          value={auth}
          onChange={(event) => setAuth(event.target.value as typeof auth)}
        >
          <option value="none">none</option>
          <option value="header">header</option>
          <option value="oauth">OAuth</option>
        </select>
      </Field>
      <Button disabled={discover.isPending || !serverUrl} onClick={() => discover.mutate()}>
        {discover.isPending ? "Discovering…" : "Discover"}
      </Button>
      <ul className="flex flex-col gap-2">
        {(discover.data?.tools ?? []).map((tool) => (
          <li key={tool.name}>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={picked.includes(tool.name)}
                onChange={(event) =>
                  setPicked((current) =>
                    event.target.checked ? [...current, tool.name] : current.filter((item) => item !== tool.name),
                  )
                }
              />
              {tool.name}
              {tool.permission ? <span className="text-muted-foreground">{tool.permission}</span> : null}
            </label>
          </li>
        ))}
      </ul>
      <Button disabled={confirm.isPending || picked.length === 0} onClick={() => confirm.mutate()}>
        {confirm.isPending ? "Adding…" : "Confirm"}
      </Button>
    </FieldGroup>
  )
}

function ApiForm({ onClose, onSaved }: { onClose: () => void; onSaved: () => Promise<void> }) {
  const [specUrl, setSpecUrl] = useState("")
  const [spec, setSpec] = useState("")
  const [authRef, setAuthRef] = useState("secret:api")
  const [picked, setPicked] = useState<string[]>([])
  const load = useMutation({
    mutationFn: () => importApiSpec(spec.trim() ? { spec, authRef } : { specUrl, authRef }),
    onError: (error) => toast.error(error instanceof Error ? error.message : "Import failed"),
  })
  const confirm = useMutation({
    mutationFn: async () => {
      const selected = (load.data?.operations ?? []).filter((operation) => picked.includes(operation.operationId))
      for (const body of operationsToTools(authRef, selected)) await createTool(body)
    },
    onSuccess: async () => {
      toast.success("API tools added")
      await onSaved()
      onClose()
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not add the tools"),
  })
  return (
    <FieldGroup>
      <Field>
        <FieldLabel htmlFor="spec-url">Spec URL</FieldLabel>
        <Input id="spec-url" value={specUrl} onChange={(event) => setSpecUrl(event.target.value)} />
      </Field>
      <Field>
        <FieldLabel htmlFor="spec-body">OpenAPI</FieldLabel>
        <textarea
          id="spec-body"
          className="min-h-24 rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm"
          value={spec}
          onChange={(event) => setSpec(event.target.value)}
        />
      </Field>
      <Field>
        <FieldLabel htmlFor="auth-ref">Auth reference</FieldLabel>
        <Input id="auth-ref" value={authRef} onChange={(event) => setAuthRef(event.target.value)} />
      </Field>
      <Button disabled={load.isPending || (!spec.trim() && !specUrl)} onClick={() => load.mutate()}>
        {load.isPending ? "Reading…" : "Preview"}
      </Button>
      <ul className="flex flex-col gap-2">
        {(load.data?.operations ?? []).map((operation) => (
          <li key={operation.operationId}>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={picked.includes(operation.operationId)}
                onChange={(event) =>
                  setPicked((current) =>
                    event.target.checked
                      ? [...current, operation.operationId]
                      : current.filter((item) => item !== operation.operationId),
                  )
                }
              />
              {operation.method} {operation.path} {operation.summary ?? operation.description}
            </label>
          </li>
        ))}
      </ul>
      <Button disabled={confirm.isPending || picked.length === 0} onClick={() => confirm.mutate()}>
        {confirm.isPending ? "Importing…" : "Confirm"}
      </Button>
    </FieldGroup>
  )
}

function DataForm({ onClose, onSaved }: { onClose: () => void; onSaved: () => Promise<void> }) {
  const [name, setName] = useState("")
  const [kind, setKind] = useState<components["schemas"]["DataSourceKind"]>("url")
  const [ref, setRef] = useState("")
  const [refreshPolicy, setRefreshPolicy] = useState<components["schemas"]["RefreshPolicy"]>("manual")
  const save = useMutation({
    mutationFn: () => createDataSource({ name, kind, ref, refreshPolicy }),
    onSuccess: async () => {
      toast.success("Source added")
      await onSaved()
      onClose()
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not add the source"),
  })
  return (
    <FieldGroup>
      <Field>
        <FieldLabel htmlFor="source-name">Name</FieldLabel>
        <Input id="source-name" value={name} onChange={(event) => setName(event.target.value)} />
      </Field>
      <Field>
        <FieldLabel htmlFor="source-kind">Kind</FieldLabel>
        <select
          id="source-kind"
          className="h-8 rounded-lg border border-input bg-transparent px-2.5 text-sm"
          value={kind}
          onChange={(event) => setKind(event.target.value as typeof kind)}
        >
          <option value="url">url</option>
          <option value="llms_txt">llms.txt</option>
          <option value="github_path">github path</option>
          <option value="upload">upload</option>
        </select>
      </Field>
      <Field>
        <FieldLabel htmlFor="source-ref">Ref</FieldLabel>
        <Input id="source-ref" value={ref} onChange={(event) => setRef(event.target.value)} />
      </Field>
      <Field>
        <FieldLabel htmlFor="source-policy">Refresh policy</FieldLabel>
        <select
          id="source-policy"
          className="h-8 rounded-lg border border-input bg-transparent px-2.5 text-sm"
          value={refreshPolicy}
          onChange={(event) => setRefreshPolicy(event.target.value as typeof refreshPolicy)}
        >
          <option value="manual">manual</option>
          <option value="weekly">weekly</option>
        </select>
      </Field>
      <Button disabled={save.isPending || !name || !ref} onClick={() => save.mutate()}>
        {save.isPending ? "Adding…" : "Add source"}
      </Button>
    </FieldGroup>
  )
}
