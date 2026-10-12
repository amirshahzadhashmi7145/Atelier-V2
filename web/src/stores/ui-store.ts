"use client"

import { create } from "zustand"

export type Theme = "light" | "dark" | "system"

type UiState = {
  theme: Theme
  selectedAgentId: string | null
  setTheme: (theme: Theme) => void
  setSelectedAgentId: (id: string | null) => void
}

export const useUiStore = create<UiState>((set) => ({
  theme: "system",
  selectedAgentId: null,
  setTheme: (theme) => set({ theme }),
  setSelectedAgentId: (selectedAgentId) => set({ selectedAgentId }),
}))
