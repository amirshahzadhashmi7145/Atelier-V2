"use client"

import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { PageHeader } from "@/components/shared/PageHeader"
import { QueryBody } from "@/components/shared/QueryBody"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { listModels, listProviders, refreshProviderModels, testProviderConnection } from "@/features/settings/api"
import { queryKeys } from "@/lib/api/query-keys"

export function ProvidersForm({ keyFound }: { keyFound: boolean }) {
  const queryClient = useQueryClient()
  const providers = useQuery({ queryKey: queryKeys.providers, queryFn: listProviders })
  const models = useQuery({ queryKey: queryKeys.models, queryFn: listModels })
  const [connection, setConnection] = useState<string | null>(null)
  const [connectionError, setConnectionError] = useState<string | null>(null)
  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.providers })
    await queryClient.invalidateQueries({ queryKey: queryKeys.models })
  }
  const test = useMutation({
    mutationFn: testProviderConnection,
    onSuccess: async (ids) => {
      setConnection("Connected")
      setConnectionError(null)
      toast.success(`Connected. ${ids.length} models.`)
      await invalidate()
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : "Connection failed"
      setConnection("failed")
      setConnectionError(message)
      toast.error(message)
    },
  })
  const refresh = useMutation({
    mutationFn: refreshProviderModels,
    onSuccess: async (items) => {
      toast.success(`${items.length} models cached`)
      await invalidate()
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Refresh failed"),
  })

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Providers" description="The key stays in .env.local. The browser never sees it." />
      <QueryBody query={providers} emptyTitle="No providers" emptyDescription="No provider is configured.">
        {(items) => (
          <div className="flex flex-col gap-4">
            {items.map((provider) => {
              const connected = connection === "Connected" || (connection !== "failed" && provider.connected)
              return (
                <Card key={provider.id}>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      {provider.name}
                      <Badge variant="secondary">{connected ? "Connected" : "Not connected"}</Badge>
                    </CardTitle>
                    <CardDescription>
                      {keyFound ? "key found" : "key missing"}
                      {provider.modelsCachedAt && (models.data ?? []).length > 0
                        ? ` · models cached ${provider.modelsCachedAt}`
                        : ""}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-4">
                    <div className="flex flex-wrap gap-2">
                      <Button type="button" variant="outline" disabled={test.isPending} onClick={() => test.mutate()}>
                        {test.isPending ? "Testing…" : "Test connection"}
                      </Button>
                      <Button type="button" variant="outline" disabled={refresh.isPending} onClick={() => refresh.mutate()}>
                        {refresh.isPending ? "Refreshing…" : "Refresh models"}
                      </Button>
                    </div>
                    {connectionError ? <p className="text-sm text-destructive">{connectionError}</p> : null}
                    <ul className="flex flex-col gap-1 text-sm">
                      {(models.data ?? []).length === 0 ? (
                        <li className="text-muted-foreground">Refresh models to load the catalog.</li>
                      ) : (
                        models.data?.map((model) => <li key={model.name}>{model.name}</li>)
                      )}
                    </ul>
                  </CardContent>
                </Card>
              )
            })}
          </div>
        )}
      </QueryBody>
    </div>
  )
}
