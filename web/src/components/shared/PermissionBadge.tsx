import { Badge } from "@/components/ui/badge"

const variant = {
  read: "secondary",
  write: "default",
  external: "outline",
} as const

export function PermissionBadge({
  permission,
}: {
  permission: keyof typeof variant
}) {
  return <Badge variant={variant[permission]}>{permission}</Badge>
}
