"use client"

import { PermissionBadge } from "@/components/shared/PermissionBadge"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Switch } from "@/components/ui/switch"

export function costNote(tool: { id: string; kind: string }) {
  if (tool.kind === "client") return "Runs in the browser"
  if (tool.kind === "mcp" || tool.kind === "api") return "Calls another server"
  if (tool.kind === "data" || tool.id === "search_data") return "Reads indexed pages"
  if (tool.id === "package_install") return "May call a package registry"
  if (tool.id === "headless_browser" || tool.id === "preview_deploy") return "Opens a network service"
  return "Runs in the sandbox"
}

export function ToolCard({
  tool,
  usedBy,
  pending,
  onEnabled,
  onConfigure,
}: {
  tool: {
    id: string
    kind: string
    name: string
    description: string
    permission: "read" | "write" | "external"
    enabled: boolean
    config: Record<string, unknown>
  }
  usedBy: number
  pending?: boolean
  onEnabled: (enabled: boolean) => void
  onConfigure: () => void
}) {
  const trust = typeof tool.config.trust === "string" ? tool.config.trust : null
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          {tool.name}
          <PermissionBadge permission={tool.permission} />
          {trust ? <Badge variant="outline">{trust}</Badge> : null}
        </CardTitle>
        <CardDescription>{tool.description}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-sm text-muted-foreground">{costNote(tool)}</p>
        <p className="text-sm">used by {usedBy} agents</p>
        {tool.kind === "client" ? <p className="text-sm">needs an open browser session</p> : null}
        <div className="flex items-center gap-2">
          <Switch
            checked={tool.enabled}
            disabled={pending}
            aria-label={`Enable ${tool.name}`}
            onCheckedChange={(checked) => onEnabled(checked)}
          />
          <Button variant="outline" size="sm" onClick={onConfigure}>
            Configure
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
