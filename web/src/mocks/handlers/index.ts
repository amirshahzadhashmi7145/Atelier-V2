import { agentHandlers } from "@/mocks/handlers/agents"
import { skillHandlers } from "@/mocks/handlers/skills"
import { toolHandlers } from "@/mocks/handlers/tools"
import { runHandlers } from "@/mocks/handlers/runs"

export const handlers = [...agentHandlers, ...toolHandlers, ...skillHandlers, ...runHandlers]
