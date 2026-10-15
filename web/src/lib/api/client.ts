import createClient from "openapi-fetch"
import type { paths } from "@/lib/api/generated/types"

export function apiBaseUrl() {
  if (process.env.NEXT_PUBLIC_USE_MOCKS === "true") {
    if (typeof window === "undefined") return "http://localhost"
    return window.location.origin
  }
  const url = process.env.NEXT_PUBLIC_API_URL
  if (!url) {
    throw new Error("NEXT_PUBLIC_API_URL is required when NEXT_PUBLIC_USE_MOCKS=false")
  }
  return url
}

export const api = createClient<paths>({
  baseUrl: apiBaseUrl(),
  fetch: async (request: Request) => {
    try {
      return await globalThis.fetch(request)
    } catch {
      const base = apiBaseUrl()
      throw new ApiError(
        `Cannot reach the API at ${base}. Start the API server (uvicorn on port 8000) and check NEXT_PUBLIC_API_URL in web/.env.local.`,
        0,
        "network",
      )
    }
  },
})

export class ApiError extends Error {
  readonly status: number
  readonly code?: string

  constructor(message: string, status: number, code?: string) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.code = code
  }
}

export async function unwrap<T>(result: {
  data?: T
  error?: unknown
  response: Response
}): Promise<T> {
  if (result.data !== undefined) return result.data
  const body = (result.error ?? {}) as { message?: string; code?: string }
  throw new ApiError(
    body.message || result.response.statusText || "Request failed",
    result.response.status,
    body.code,
  )
}
