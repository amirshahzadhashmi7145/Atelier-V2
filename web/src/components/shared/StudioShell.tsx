"use client"

import { useEffect } from "react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { BotIcon, LibraryIcon, MonitorIcon, MoonIcon, PlayIcon, PlusIcon, SettingsIcon, SunIcon, Trash2Icon, WrenchIcon } from "lucide-react"
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
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { api, unwrap } from "@/lib/api/client"
import { queryKeys } from "@/lib/api/query-keys"
import { useUiStore, type Theme } from "@/stores/ui-store"

const studioItems = [
  { href: "/agents", label: "Agents", icon: BotIcon },
  { href: "/tools", label: "Tools", icon: WrenchIcon },
  { href: "/skills", label: "Skills", icon: LibraryIcon },
  { href: "/runs", label: "Runs", icon: PlayIcon },
  { href: "/settings/providers", label: "Settings", icon: SettingsIcon },
]

const themeOptions: { value: Theme; label: string; icon: typeof SunIcon }[] = [
  { value: "light", label: "Light theme", icon: SunIcon },
  { value: "dark", label: "Dark theme", icon: MoonIcon },
  { value: "system", label: "Match system theme", icon: MonitorIcon },
]

const settingsSections: Record<string, string> = {
  providers: "Providers",
  github: "GitHub",
  runs: "Runs",
  models: "Models",
  roles: "Roles",
}

/** Where the reader is, as a short trail: the section, then the page inside it. */
function locationTrail(pathname: string): string[] {
  const [section, sub] = pathname.split("/").filter(Boolean)
  if (section === "chat") return [sub ? "Chat" : "New chat"]
  if (section === "settings") return ["Settings", ...(sub && settingsSections[sub] ? [settingsSections[sub]] : [])]
  const item = studioItems.find((entry) => entry.href === `/${section}`)
  if (!item) return ["Studio"]
  if (sub === "new") return [item.label, `New ${item.label.toLowerCase().replace(/s$/, "")}`]
  return [item.label]
}

function ChatHistory({ activeId }: { activeId: string | null }) {
  const router = useRouter()
  const queryClient = useQueryClient()
  const projects = useQuery({
    queryKey: queryKeys.chatHistory,
    queryFn: async () => unwrap(await api.GET("/projects")),
    // A low-frequency refresh keeps new/renamed chats appearing without piggy-backing
    // on the active chat's project key (which would cancel its in-flight polling).
    refetchInterval: 5000,
    refetchOnWindowFocus: false,
  })
  const rows = projects.data ?? []
  const remove = useMutation({
    mutationFn: async (id: string) => unwrap(await api.DELETE("/projects/{id}", { params: { path: { id } } })),
    onSuccess: async (_data, id) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.chatHistory })
      toast.success("Chat deleted")
      if (id === activeId) router.push("/chat")
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not delete the chat"),
  })
  return (
    <SidebarGroup>
      <SidebarGroupLabel>Chats</SidebarGroupLabel>
      <SidebarGroupContent>
        {projects.isLoading ? (
          <p className="px-2 py-1 text-xs text-muted-foreground">Loading…</p>
        ) : rows.length === 0 ? (
          <p className="px-2 py-1 text-xs text-muted-foreground">No chats yet</p>
        ) : (
          <SidebarMenu>
            {rows.map((item) => (
              <SidebarMenuItem key={item.id}>
                <SidebarMenuButton
                  isActive={item.id === activeId}
                  render={<Link href={`/chat/${item.id}`} />}
                >
                  <span className="truncate">{item.name}</span>
                </SidebarMenuButton>
                <SidebarMenuAction
                  aria-label={`Delete ${item.name}`}
                  title="Delete chat"
                  showOnHover
                  onClick={() => {
                    if (window.confirm(`Delete “${item.name}”? Files on disk are kept.`)) remove.mutate(item.id)
                  }}
                >
                  <Trash2Icon />
                </SidebarMenuAction>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        )}
      </SidebarGroupContent>
    </SidebarGroup>
  )
}

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
  const activeChatId = pathname.startsWith("/chat/") ? pathname.split("/")[2] || null : null
  const trail = locationTrail(pathname)

  return (
    <SidebarProvider className="h-dvh min-h-0 overflow-hidden">
      <ThemeClass />
      <Sidebar>
        <nav aria-label="Studio" className="flex h-full min-h-0 flex-col">
          <SidebarHeader className="gap-3 px-3 py-3">
            <span className="px-1 text-sm font-semibold tracking-tight">Agent Studio</span>
            <SidebarMenuButton
              className="justify-start gap-2 border bg-background font-medium shadow-sm hover:bg-accent"
              render={<Link href="/chat" />}
            >
              <PlusIcon className="size-4" />
              <span>New chat</span>
            </SidebarMenuButton>
          </SidebarHeader>
          <SidebarContent>
            <ChatHistory activeId={activeChatId} />
            <SidebarGroup>
              <SidebarGroupLabel>Studio</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {studioItems.map((item) => (
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
              {themeOptions.map((option) => (
                <ToggleGroupItem key={option.value} value={option.value} aria-label={option.label} title={option.label}>
                  <option.icon aria-hidden="true" />
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </SidebarFooter>
        </nav>
      </Sidebar>
      <SidebarInset className="min-h-0 overflow-hidden">
        <header className="flex h-12 shrink-0 items-center gap-2 border-b px-4">
          <SidebarTrigger />
          <ol aria-label="Location" className="flex min-w-0 items-center gap-1.5 text-sm">
            {trail.map((part, index) => (
              <li key={part} className="flex min-w-0 items-center gap-1.5">
                {index > 0 ? <span aria-hidden="true" className="text-muted-foreground/60">/</span> : null}
                <span className={index === trail.length - 1 ? "truncate font-medium" : "truncate text-muted-foreground"}>
                  {part}
                </span>
              </li>
            ))}
          </ol>
        </header>
        {pathname.startsWith("/chat") ? (
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden">{children}</div>
        ) : (
          <div className="min-h-0 flex-1 overflow-auto">
            {/* Every studio page uses the full width of the window. */}
            <div className="flex min-h-full w-full flex-col gap-6 px-6 py-8">
              {children}
            </div>
          </div>
        )}
      </SidebarInset>
      <Toaster theme={theme} />
    </SidebarProvider>
  )
}
