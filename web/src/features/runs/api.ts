import { api, unwrap } from "@/lib/api/client"

export async function listRuns(page = 1) {
  return unwrap(await api.GET("/runs", { params: { query: { page } } }))
}
