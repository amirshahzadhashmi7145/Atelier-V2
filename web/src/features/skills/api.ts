import { api, unwrap } from "@/lib/api/client"

export async function listSkills() {
  return unwrap(await api.GET("/skills"))
}
