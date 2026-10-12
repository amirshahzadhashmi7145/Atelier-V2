import { api, unwrap } from "@/lib/api/client"

export async function listAgents() {
  return unwrap(await api.GET("/agents"))
}
