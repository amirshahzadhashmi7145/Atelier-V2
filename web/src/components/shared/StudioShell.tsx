"use client"

import { useEffect } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { BotIcon, LibraryIcon, PlayIcon, SettingsIcon, WrenchIcon } from "lucide-react"
import { Toaster } from "@/components/ui/sonner"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { useUiStore, type Theme } from "@/stores/ui-store"

const items = [
  { href: "/agents", label: "Agents", icon: BotIcon },
  { href: "/tools", label: "Tools", icon: WrenchIcon },
  { href: "/skills", label: "Skills", icon: LibraryIcon },
  { href: "/runs", label: "Runs", icon: PlayIcon },
  { href: "/settings/providers", label: "Settings", icon: SettingsIcon },
]

function ThemeClass() {
  const theme = useUiStore((state) => state.theme)
  useEffect(() => {
    const root = document.documentElement
    const apply = () => {
      const dark =
        theme === "dark" ||
        (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches)
      root.classList.toggle("dark", dark)
    }
    apply()
    if (theme !== "system") return
    const media = window.matchMedia("(prefers-color-scheme: dark)")
    media.addEventListener("change", apply)
    return () => media.removeEventListener("change", apply)
  }, [theme])
  return null
}

export function StudioShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const theme = useUiStore((state) => state.theme)
  const setTheme = useUiStore((state) => state.setTheme)

  return (
    <SidebarProvider>
      <ThemeClass />
      <Sidebar>
        <nav aria-label="Studio" className="flex h-full min-h-0 flex-col">
          <SidebarHeader className="px-4 py-3">
            <span className="text-sm font-semibold tracking-tight">Agent Studio</span>
          </SidebarHeader>
          <SidebarContent>
            <SidebarGroup>
              <SidebarGroupLabel>Studio</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {items.map((item) => (
                    <SidebarMenuItem key={item.href}>
                      <SidebarMenuButton
                        isActive={pathname === item.href || pathname.startsWith(`${item.href}/`)}
                        render={<Link href={item.href} />}
                      >
                        <item.icon />
                        <span>{item.label}</span>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  ))}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          </SidebarContent>
          <SidebarFooter className="p-3">
            <ToggleGroup
              variant="outline"
              size="sm"
              spacing={0}
              value={[theme]}
              onValueChange={(value: string[]) => {
                const next = value.at(-1)
                if (next === "light" || next === "dark" || next === "system") setTheme(next)
              }}
              aria-label="Theme"
            >
              {(["light", "dark", "system"] as Theme[]).map((option) => (
                <ToggleGroupItem key={option} value={option} aria-label={option}>
                  {option}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </SidebarFooter>
        </nav>
      </Sidebar>
      <SidebarInset>
        <header className="flex items-center gap-2 border-b px-4 py-3">
          <SidebarTrigger />
          <span className="text-sm text-muted-foreground">Studio</span>
        </header>
        <div className="flex flex-1 flex-col gap-6 p-6">{children}</div>
      </SidebarInset>
      <Toaster theme={theme} />
    </SidebarProvider>
  )
}
