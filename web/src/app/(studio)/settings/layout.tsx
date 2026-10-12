import Link from "next/link"

export const instant = false

const links = [
  ["/settings/providers", "Providers"],
  ["/settings/runs", "Runs"],
  ["/settings/models", "Models"],
] as const

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-6">
      <nav className="flex gap-3 text-sm">
        {links.map(([href, label]) => (
          <Link key={href} href={href} className="underline">
            {label}
          </Link>
        ))}
      </nav>
      {children}
    </div>
  )
}
