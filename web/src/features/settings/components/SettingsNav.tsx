"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "cn"

const links = [
  ["/settings/providers", "Providers"],
  ["/settings/github", "GitHub"],
  ["/settings/runs", "Runs"],
  ["/settings/models", "Models"],
  ["/settings/roles", "Roles"],
] as const

export function SettingsNav() {
  const pathname = usePathname()
  return (
    <nav aria-label="Settings" className="no-scrollbar -mb-px flex gap-5 overflow-x-auto border-b text-sm">
      {links.map(([href, label]) => {
        const active = pathname === href || pathname.startsWith(`${href}/`)
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "-mb-px shrink-0 border-b-2 px-0.5 pb-2.5 pt-1 font-medium outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50",
              active
                ? "border-foreground text-foreground"
                : "border-transparent text-muted-foreground hover:border-border hover:text-foreground",
            )}
          >
            {label}
          </Link>
        )
      })}
    </nav>
  )
}
