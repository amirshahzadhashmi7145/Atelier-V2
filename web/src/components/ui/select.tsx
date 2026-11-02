"use client"

import * as React from "react"
import { Select as SelectPrimitive } from "@base-ui/react/select"
import { Check, ChevronDown } from "lucide-react"
import { cn } from "cn"

export type SelectOption = { value: string; label: string; group?: string }

/**
 * A styled single-select built on Base UI. Renders a translucent, blurred popup
 * (so it reads as a floating panel over the page), groups options under optional
 * headers, and stays readable in light and dark mode. Replaces native <select>,
 * whose option popups cannot be themed or given a translucent background.
 */
export function Select({
  id,
  value,
  onValueChange,
  options,
  placeholder = "Select…",
  disabled,
  ariaLabel,
  className,
}: {
  id?: string
  value: string
  onValueChange: (value: string) => void
  options: SelectOption[]
  placeholder?: string
  disabled?: boolean
  ariaLabel?: string
  className?: string
}) {
  const labels = React.useMemo(
    () => Object.fromEntries(options.map((option) => [option.value, option.label])),
    [options],
  )
  const groups = React.useMemo(() => {
    const order: string[] = []
    const byGroup: Record<string, SelectOption[]> = {}
    for (const option of options) {
      const key = option.group ?? ""
      if (!(key in byGroup)) {
        byGroup[key] = []
        order.push(key)
      }
      byGroup[key].push(option)
    }
    return order.map((group) => ({ group, items: byGroup[group] }))
  }, [options])

  return (
    <SelectPrimitive.Root value={value} onValueChange={(next) => onValueChange((next as string) ?? "")}>
      <SelectPrimitive.Trigger
        id={id}
        aria-label={ariaLabel}
        disabled={disabled}
        className={cn(
          "flex h-9 w-full items-center justify-between gap-2 rounded-lg border border-input bg-transparent px-3 py-1 text-sm outline-none transition-colors",
          "hover:border-ring/60 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/40",
          "disabled:pointer-events-none disabled:opacity-50 dark:bg-input/30",
          className,
        )}
      >
        <span className="truncate text-left">
          {value ? labels[value] ?? value : <span className="text-muted-foreground">{placeholder}</span>}
        </span>
        <SelectPrimitive.Icon className="shrink-0 text-muted-foreground">
          <ChevronDown className="size-4" />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Positioner className="z-50 outline-none" sideOffset={6} alignItemWithTrigger={false}>
          <SelectPrimitive.Popup
            className={cn(
              "max-h-72 min-w-[14rem] overflow-y-auto rounded-xl border border-border/70 p-1 shadow-xl",
              "bg-popover/80 text-popover-foreground backdrop-blur-md",
              "origin-[var(--transform-origin)] transition-[transform,opacity] data-[starting-style]:scale-95 data-[starting-style]:opacity-0",
            )}
          >
            {groups.map(({ group, items }) => (
              <SelectPrimitive.Group key={group || "_ungrouped"}>
                {group ? (
                  <SelectPrimitive.GroupLabel className="px-2 pb-1 pt-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {group}
                  </SelectPrimitive.GroupLabel>
                ) : null}
                {items.map((option) => (
                  <SelectPrimitive.Item
                    key={option.value}
                    value={option.value}
                    className={cn(
                      "flex cursor-pointer select-none items-center justify-between gap-2 rounded-md px-2 py-1.5 text-sm outline-none",
                      "data-[highlighted]:bg-accent data-[highlighted]:text-accent-foreground",
                    )}
                  >
                    <SelectPrimitive.ItemText>{option.label}</SelectPrimitive.ItemText>
                    <SelectPrimitive.ItemIndicator className="text-primary">
                      <Check className="size-4" />
                    </SelectPrimitive.ItemIndicator>
                  </SelectPrimitive.Item>
                ))}
              </SelectPrimitive.Group>
            ))}
          </SelectPrimitive.Popup>
        </SelectPrimitive.Positioner>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  )
}
