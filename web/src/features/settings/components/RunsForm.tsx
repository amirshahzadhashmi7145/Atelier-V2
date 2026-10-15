"use client"

import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { PageHeader } from "@/components/shared/PageHeader"
import { QueryBody } from "@/components/shared/QueryBody"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { getRunSettings, saveRunSettings } from "@/features/settings/api"
import { queryKeys } from "@/lib/api/query-keys"

export function RunsForm() {
  const queryClient = useQueryClient()
  const settings = useQuery({ queryKey: queryKeys.runSettings, queryFn: getRunSettings })
  const [spend, setSpend] = useState<string | null>(null)
  const [iterations, setIterations] = useState<string | null>(null)
  const [minutes, setMinutes] = useState<string | null>(null)
  const [loop, setLoop] = useState<boolean | null>(null)
  const [recordRequests, setRecordRequests] = useState<boolean | null>(null)
  const save = useMutation({
    mutationFn: saveRunSettings,
    onSuccess: async () => {
      toast.success("Run settings saved")
      await queryClient.invalidateQueries({ queryKey: queryKeys.runSettings })
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Save failed"),
  })

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Runs" description="A run ends when the task is complete or a bound is hit." />
      <QueryBody query={settings} emptyTitle="No run settings" emptyDescription="Platform defaults are missing.">
        {(current) => {
          const maxSpendPerRunUsd = Number(spend ?? current.maxSpendPerRunUsd)
          const maxIterations = Number(iterations ?? current.maxIterations)
          const maxMinutes = Number(minutes ?? current.maxMinutes)
          const loopDetection = loop ?? current.loopDetection
          const recordModelRequests = recordRequests ?? current.recordModelRequests ?? false
          return (
            <Card>
              <CardHeader>
                <CardTitle>Platform defaults</CardTitle>
                <CardDescription>These apply to every run.</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <Field>
                  <FieldLabel htmlFor="max-spend">Max spend per run</FieldLabel>
                  <Input
                    id="max-spend"
                    type="number"
                    min={0}
                    step="0.01"
                    value={spend ?? String(current.maxSpendPerRunUsd)}
                    onChange={(event) => setSpend(event.target.value)}
                  />
                </Field>
                <details className="flex flex-col gap-4">
                  <summary className="cursor-pointer text-sm font-medium">Advanced</summary>
                  <div className="flex flex-col gap-4 pt-4">
                    <Field>
                      <FieldLabel htmlFor="max-iterations">Max iterations</FieldLabel>
                      <Input
                        id="max-iterations"
                        type="number"
                        min={1}
                        value={iterations ?? String(current.maxIterations)}
                        onChange={(event) => setIterations(event.target.value)}
                      />
                    </Field>
                    <Field>
                      <FieldLabel htmlFor="max-minutes">Max minutes</FieldLabel>
                      <Input
                        id="max-minutes"
                        type="number"
                        min={1}
                        value={minutes ?? String(current.maxMinutes)}
                        onChange={(event) => setMinutes(event.target.value)}
                      />
                    </Field>
                    <Field orientation="horizontal">
                      <input
                        id="loop-detection"
                        type="checkbox"
                        checked={loopDetection}
                        onChange={(event) => setLoop(event.target.checked)}
                      />
                      <FieldLabel htmlFor="loop-detection">Loop detection</FieldLabel>
                    </Field>
                    <Field orientation="horizontal">
                      <input
                        id="record-model-requests"
                        type="checkbox"
                        checked={recordModelRequests}
                        onChange={(event) => setRecordRequests(event.target.checked)}
                      />
                      <FieldLabel htmlFor="record-model-requests">Record model requests</FieldLabel>
                    </Field>
                  </div>
                </details>
                <Button
                  type="button"
                  disabled={save.isPending}
                  onClick={() =>
                    save.mutate({ maxSpendPerRunUsd, maxIterations, maxMinutes, loopDetection, recordModelRequests })
                  }
                >
                  {save.isPending ? "Saving…" : "Save"}
                </Button>
              </CardContent>
            </Card>
          )
        }}
      </QueryBody>
    </div>
  )
}
