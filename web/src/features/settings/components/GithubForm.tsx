"use client"

import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { PageHeader } from "@/components/shared/PageHeader"
import { QueryBody } from "@/components/shared/QueryBody"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { disconnectGithub, getGithubSettings, saveGithubSettings } from "@/features/settings/api"
import { queryKeys } from "@/lib/api/query-keys"

export function GithubForm() {
  const queryClient = useQueryClient()
  const settings = useQuery({ queryKey: queryKeys.githubSettings, queryFn: getGithubSettings })
  const [token, setToken] = useState("")
  const invalidate = () => queryClient.invalidateQueries({ queryKey: queryKeys.githubSettings })

  const save = useMutation({
    mutationFn: () => saveGithubSettings(token.trim()),
    onSuccess: async (data) => {
      setToken("")
      toast.success(data.login ? `Connected as ${data.login}` : "GitHub connected")
      await invalidate()
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not connect GitHub"),
  })
  const remove = useMutation({
    mutationFn: disconnectGithub,
    onSuccess: async () => {
      toast.success("GitHub disconnected")
      await invalidate()
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not disconnect"),
  })

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="GitHub"
        description="Connect GitHub once for the whole studio. Agents push and open pull requests on request — you never paste a token per project."
      />
      <QueryBody query={settings} emptyTitle="" emptyDescription="">
        {(data) => (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                Connection
                {data.connected ? (
                  <Badge variant="secondary" data-github-connected>
                    {data.login ? `Connected as ${data.login}` : "Connected"}
                  </Badge>
                ) : (
                  <Badge variant="outline">Not connected</Badge>
                )}
              </CardTitle>
              <CardDescription>
                Use a fine-grained or classic personal access token with <strong>repository contents: read &amp; write</strong>{" "}
                (and <strong>pull requests</strong> if you want PRs). The token is encrypted at rest and never shown again.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <form
                className="flex flex-col gap-2 sm:flex-row sm:items-end"
                onSubmit={(event) => {
                  event.preventDefault()
                  if (token.trim()) save.mutate()
                }}
              >
                <label className="flex flex-1 flex-col gap-1 text-sm">
                  <span className="font-medium">
                    {data.connected ? "Replace token" : "Personal access token"}
                    {data.hint ? <span className="ml-1 font-normal text-muted-foreground">(saved: {data.hint})</span> : null}
                  </span>
                  <Input
                    type="password"
                    autoComplete="off"
                    placeholder="ghp_… or github_pat_…"
                    value={token}
                    onChange={(event) => setToken(event.target.value)}
                  />
                </label>
                <Button type="submit" disabled={!token.trim() || save.isPending}>
                  {save.isPending ? "Connecting…" : data.connected ? "Update token" : "Connect GitHub"}
                </Button>
              </form>
              {data.connected ? (
                <div>
                  <Button type="button" variant="outline" disabled={remove.isPending} onClick={() => remove.mutate()}>
                    {remove.isPending ? "Disconnecting…" : "Disconnect"}
                  </Button>
                </div>
              ) : null}
              <p className="text-xs text-muted-foreground">
                Once connected, just tell an agent in chat: “push this to GitHub” or “open a pull request”. It will ask which
                repository to use if one isn’t set yet.
              </p>
            </CardContent>
          </Card>
        )}
      </QueryBody>
    </div>
  )
}
