"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { parseSkillMarkdown } from "@/features/skills/frontmatter"
import { createSkill, importSkillRepo, postSkillZip } from "@/features/skills/api"
import { ImportReview } from "@/features/skills/components/ImportReview"
import type { components } from "@/lib/api/generated/types"
import { queryKeys } from "@/lib/api/query-keys"

type Preview = components["schemas"]["SkillImportResult"]

export function ImportSheet() {
  const router = useRouter()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [repoUrl, setRepoUrl] = useState("https://github.com/vercel-labs/agent-skills")
  const [path, setPath] = useState("skills/react-best-practices")
  const [preview, setPreview] = useState<Preview | null>(null)
  const [folder, setFolder] = useState<{ name: string; description: string; body: string; files: { name: string; size: number }[]; origin: string } | null>(null)

  const saved = async (id: string) => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.skills })
    toast.success("Skill imported")
    setOpen(false)
    setPreview(null)
    setFolder(null)
    router.push(`/skills/${id}`)
  }
  const fail = (error: unknown) => toast.error(error instanceof Error ? error.message : "Import failed")

  const reviewRepo = useMutation({
    mutationFn: () => importSkillRepo(repoUrl, path, true),
    onSuccess: (result) => {
      setFolder(null)
      setPreview(result)
    },
    onError: fail,
  })
  const confirmRepo = useMutation({
    mutationFn: () => importSkillRepo(repoUrl, path, false),
    onSuccess: (result) => void saved(result.skill.id),
    onError: fail,
  })
  const reviewZip = useMutation({
    mutationFn: (file: File) => postSkillZip(file, true),
    onSuccess: (result) => {
      setFolder(null)
      setPreview(result)
    },
    onError: fail,
  })
  const confirmZip = useMutation({
    mutationFn: (file: File) => postSkillZip(file, false),
    onSuccess: (result) => void saved(result.skill.id),
    onError: fail,
  })
  const confirmFolder = useMutation({
    mutationFn: () => {
      if (!folder) throw new Error("Choose a folder")
      return createSkill(folder)
    },
    onSuccess: (skill) => void saved(skill.id),
    onError: fail,
  })
  const [zip, setZip] = useState<File | null>(null)

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        Import
      </Button>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent className="overflow-auto sm:max-w-md">
          <SheetHeader>
            <SheetTitle>Import a skill</SheetTitle>
          </SheetHeader>
          <FieldGroup className="px-4">
            <Field>
              <FieldLabel htmlFor="repo-url">GitHub URL</FieldLabel>
              <Input id="repo-url" value={repoUrl} onChange={(event) => setRepoUrl(event.target.value)} />
            </Field>
            <Field>
              <FieldLabel htmlFor="repo-path">Folder path</FieldLabel>
              <Input id="repo-path" value={path} onChange={(event) => setPath(event.target.value)} />
            </Field>
            <Button disabled={reviewRepo.isPending} onClick={() => reviewRepo.mutate()}>
              {reviewRepo.isPending ? "Reading…" : "Preview"}
            </Button>
            <Field>
              <FieldLabel htmlFor="skill-zip">Zip</FieldLabel>
              <Input
                id="skill-zip"
                type="file"
                accept=".zip,application/zip"
                onChange={(event) => {
                  const file = event.target.files?.[0]
                  if (!file) return
                  setZip(file)
                  reviewZip.mutate(file)
                }}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="skill-folder">Folder</FieldLabel>
              <Input
                id="skill-folder"
                type="file"
                multiple
                ref={(node) => node?.setAttribute("webkitdirectory", "")}
                onChange={(event) => {
                  void readFolder(event.target.files)
                    .then((next) => {
                      setPreview(null)
                      setFolder(next)
                    })
                    .catch(fail)
                }}
              />
            </Field>
          </FieldGroup>
          <div className="px-4 pb-4">
            {preview ? (
              <ImportReview
                name={preview.skill.name}
                description={preview.skill.description}
                body={preview.skill.body}
                files={preview.skill.files}
                diff={preview.diff}
                pending={confirmRepo.isPending || confirmZip.isPending}
                onConfirm={() => (zip && preview.skill.origin.startsWith("zip:") ? confirmZip.mutate(zip) : confirmRepo.mutate())}
              />
            ) : null}
            {folder ? (
              <ImportReview
                name={folder.name}
                description={folder.description}
                body={folder.body}
                files={folder.files}
                diff={[]}
                pending={confirmFolder.isPending}
                onConfirm={() => confirmFolder.mutate()}
              />
            ) : null}
          </div>
        </SheetContent>
      </Sheet>
    </>
  )
}

async function readFolder(list: FileList | null) {
  const files = [...(list ?? [])]
  const skill = files.find((file) => file.name === "SKILL.md")
  if (!skill) throw new Error("Folder has no SKILL.md")
  const parsed = parseSkillMarkdown(await skill.text())
  const root = skill.webkitRelativePath.split("/")[0] || "upload"
  return {
    ...parsed,
    origin: `folder:${root}`,
    files: files.filter((file) => file !== skill).map((file) => ({ name: file.name, size: file.size })),
  }
}
