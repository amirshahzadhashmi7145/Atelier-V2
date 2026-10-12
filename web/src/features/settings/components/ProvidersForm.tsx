"use client"

import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useForm } from "react-hook-form"
import { toast } from "sonner"
import { z } from "zod"
import { PageHeader } from "@/components/shared/PageHeader"
import { QueryBody } from "@/components/shared/QueryBody"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { listModels, listProviders, refreshModels, saveProviderKey, testProvider } from "@/features/settings/api"
import { queryKeys } from "@/lib/api/query-keys"

const keySchema = z.object({ apiKey: z.string().min(1, "Enter a key") })

export function ProvidersForm() {
  const queryClient = useQueryClient()
  const providers = useQuery({ queryKey: queryKeys.providers, queryFn: listProviders })
  const models = useQuery({ queryKey: queryKeys.models, queryFn: listModels })
  const form = useForm({ defaultValues: { apiKey: "" } })
  const [formKey, setFormKey] = useState(0)
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.providers })
    void queryClient.invalidateQueries({ queryKey: queryKeys.models })
  }
  const save = useMutation({
    mutationFn: (apiKey: string) => saveProviderKey("openai", apiKey),
    onSuccess: () => {
      form.reset()
      setFormKey((value) => value + 1)
      toast.success("Key stored")
      invalidate()
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not store the key"),
  })
  const test = useMutation({
    mutationFn: () => testProvider("openai"),
    onSuccess: (provider) => {
      toast.success(provider.connected ? "Connected" : "Not connected")
      invalidate()
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Connection failed"),
  })
  const refresh = useMutation({
    mutationFn: () => refreshModels("openai"),
    onSuccess: (items) => {
      toast.success(`${items.length} models cached`)
      invalidate()
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Refresh failed"),
  })

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Providers" description="Keys stay in the secret store. The studio only keeps a reference." />
      <QueryBody query={providers} emptyTitle="No providers" emptyDescription="No provider is configured.">
        {(items) => (
          <div className="flex flex-col gap-4">
            {items.map((provider) => (
              <Card key={provider.id}>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    {provider.name}
                    <Badge variant="secondary">{provider.connected ? "Connected" : "Not connected"}</Badge>
                  </CardTitle>
                  <CardDescription>
                    {provider.keyRef ? `Key reference ${provider.keyRef}` : "No key stored"}
                    {provider.modelsCachedAt ? ` · models cached ${provider.modelsCachedAt}` : ""}
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex flex-col gap-4">
                  <form
                    className="flex flex-col gap-3"
                    onSubmit={form.handleSubmit((values) => {
                      const parsed = keySchema.safeParse(values)
                      if (!parsed.success) {
                        toast.error(parsed.error.issues[0]?.message ?? "Enter a key")
                        return
                      }
                      save.mutate(parsed.data.apiKey)
                    })}
                  >
                    <FieldGroup>
                      <Field>
                        <FieldLabel htmlFor="apiKey">API key</FieldLabel>
                        <Input
                          key={formKey}
                          id="apiKey"
                          type="password"
                          autoComplete="off"
                          onChange={(event) => form.setValue("apiKey", event.target.value)}
                        />
                      </Field>
                    </FieldGroup>
                    <div className="flex flex-wrap gap-2">
                      <Button type="submit" disabled={save.isPending}>
                        {save.isPending ? "Saving…" : "Save key"}
                      </Button>
                      <Button type="button" variant="outline" disabled={test.isPending} onClick={() => test.mutate()}>
                        {test.isPending ? "Testing…" : "Test connection"}
                      </Button>
                      <Button type="button" variant="outline" disabled={refresh.isPending} onClick={() => refresh.mutate()}>
                        {refresh.isPending ? "Refreshing…" : "Refresh models"}
                      </Button>
                    </div>
                  </form>
                  <ul className="flex flex-col gap-1 text-sm">
                    {(models.data ?? []).length === 0 ? (
                      <li className="text-muted-foreground">Refresh models to load the catalog.</li>
                    ) : (
                      models.data?.map((model) => <li key={model.name}>{model.name}</li>)
                    )}
                  </ul>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </QueryBody>
    </div>
  )
}
