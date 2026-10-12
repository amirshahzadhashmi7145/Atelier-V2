"use client"

import { useRouter } from "next/navigation"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { QueryBody } from "@/components/shared/QueryBody"
import { createSkill, getSkill, listSkillAgents, updateSkill } from "@/features/skills/api"
import { SkillEditor, type SkillDraft } from "@/features/skills/components/SkillEditor"
import { queryKeys } from "@/lib/api/query-keys"

const blank: SkillDraft = {
  name: "",
  description: "",
  body: "",
  files: [],
  versions: [],
  origin: "studio",
}

export function SkillScreen({ id }: { id?: string }) {
  const router = useRouter()
  const queryClient = useQueryClient()
  const skill = useQuery({
    queryKey: [...queryKeys.skills, id],
    queryFn: () => getSkill(id ?? ""),
    enabled: Boolean(id),
  })
  const agents = useQuery({ queryKey: queryKeys.agents, queryFn: listSkillAgents })
  const save = useMutation({
    mutationFn: (draft: SkillDraft) => {
      const body = { name: draft.name, description: draft.description, body: draft.body, files: draft.files }
      return id ? updateSkill(id, body) : createSkill({ ...body, origin: draft.origin })
    },
    onSuccess: async (next) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.skills })
      toast.success("Skill saved")
      if (!id) router.push(`/skills/${next.id}`)
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not save the skill"),
  })

  const editor = (initial: SkillDraft, skillId?: string) => (
    <SkillEditor
      key={`${skillId ?? "new"}-${initial.versions.length}`}
      initial={initial}
      agents={(agents.data ?? [])
        .filter((agent) => (skillId ? agent.skillIds.includes(skillId) : false))
        .map((agent) => ({ id: agent.id, name: agent.name }))}
      pending={save.isPending}
      onSave={(draft) => save.mutate(draft)}
    />
  )

  if (!id) return editor(blank)
  return (
    <QueryBody query={skill} emptyTitle="Skill not found" emptyDescription="That skill is not in the studio.">
      {(item) => editor(item, item.id)}
    </QueryBody>
  )
}
