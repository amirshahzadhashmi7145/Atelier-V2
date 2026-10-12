"use client"

import { create } from "zustand"

export type Theme = "light" | "dark" | "system"

type UiState = {
  theme: Theme
  selectedAgentId: string | null
  runListAgent: string
  runListStatus: string
  runListPage: number
  leftPane: number
  rightPane: number
  setTheme: (theme: Theme) => void
  setSelectedAgentId: (id: string | null) => void
  setRunList: (patch: Partial<Pick<UiState, "runListAgent" | "runListStatus" | "runListPage">>) => void
  setPane: (side: "left" | "right", width: number) => void
}

export const useUiStore = create<UiState>((set) => ({
  theme: "system",
  selectedAgentId: null,
  runListAgent: "",
  runListStatus: "",
  runListPage: 1,
  leftPane: 340,
  rightPane: 320,
  setTheme: (theme) => set({ theme }),
  setSelectedAgentId: (selectedAgentId) => set({ selectedAgentId }),
  setRunList: (patch) => set(patch),
  setPane: (side, width) => set(side === "left" ? { leftPane: width } : { rightPane: width }),
}))
