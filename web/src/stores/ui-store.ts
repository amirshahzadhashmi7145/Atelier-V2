"use client"

import { create } from "zustand"

export type Theme = "light" | "dark" | "system"

type UiState = {
  theme: Theme
  setTheme: (theme: Theme) => void
}

export const useUiStore = create<UiState>((set) => ({
  theme: "system",
  setTheme: (theme) => set({ theme }),
}))
