import { agentHandlers } from "@/mocks/handlers/agents"
import { libraryHandlers } from "@/mocks/handlers/library"
import { providerHandlers } from "@/mocks/handlers/providers"
import { roleHandlers } from "@/mocks/handlers/roles"
import { skillHandlers } from "@/mocks/handlers/skills"
import { toolHandlers } from "@/mocks/handlers/tools"
import { runHandlers } from "@/mocks/handlers/runs"

export const handlers = [
  ...agentHandlers,
  ...toolHandlers,
  ...skillHandlers,
  ...runHandlers,
  ...libraryHandlers,
  ...providerHandlers,
  ...roleHandlers,
]
