import { api, unwrap } from "@/lib/api/client"

export async function listTools() {
  return unwrap(await api.GET("/tools"))
}
