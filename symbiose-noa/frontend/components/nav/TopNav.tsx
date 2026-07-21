"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { signOut } from "next-auth/react"
import { useState, useEffect, useRef } from "react"
import { getVisibleTabs } from "@/lib/permissions"

interface Props {
  role: string
  email: string
  name: string
}

export default function TopNav({ role, email, name }: Props) {
  const pathname = usePathname()
  const tabs = getVisibleTabs(role)
  const [showDropdown, setShowDropdown] = useState(false)
  const dropRef = useRef<HTMLDivElement>(null)

  const initials = name
    .split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase() || name.slice(0, 2).toUpperCase()

  useEffect(() => {
    if (!showDropdown) return
    const close = (e: MouseEvent) => {
      if (dropRef.current && !dropRef.current.contains(e.target as Node)) {
        setShowDropdown(false)
      }
    }
    document.addEventListener("mousedown", close)
    return () => document.removeEventListener("mousedown", close)
  }, [showDropdown])

  return (
    <nav
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        height: 64,
        background: "var(--color-surface)",
        borderBottom: "1px solid var(--color-border)",
        display: "flex",
        alignItems: "center",
        padding: "0 28px",
        zIndex: 100,
        gap: 0,
      }}
    >
      {/* Logo */}
      <Link
        href="/accueil"
        style={{ marginRight: 36, flexShrink: 0, display: "flex", alignItems: "center" }}
      >
        <img
          src="/symbiose-paysage.svg"
          alt="Symbiose Paysage"
          style={{ height: 34, width: "auto", display: "block" }}
        />
      </Link>

      {/* Tabs */}
      <div
        style={{
          display: "flex",
          gap: 2,
          flex: 1,
          alignItems: "center",
          overflowX: "auto",
          scrollbarWidth: "none",
        }}
      >
        {tabs.map((tab) => {
          const isActive =
            pathname === tab.href || pathname.startsWith(tab.href + "/")
          return (
            <Link
              key={tab.key}
              href={tab.href}
              style={{
                padding: "7px 14px",
                fontSize: 14,
                fontWeight: isActive ? 600 : 500,
                color: isActive
                  ? "var(--color-primary)"
                  : "var(--color-text-body)",
                borderRadius: 9,
                background: isActive
                  ? "var(--color-primary-subtle)"
                  : "transparent",
                transition: "all 0.15s ease",
                whiteSpace: "nowrap",
                flexShrink: 0,
              }}
            >
              {tab.label}
            </Link>
          )
        })}
      </div>

      {/* Right side */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          flexShrink: 0,
          marginLeft: 16,
        }}
      >
        {/* Avatar + dropdown */}
        <div style={{ position: "relative" }} ref={dropRef}>
          <button
            onClick={() => setShowDropdown((v) => !v)}
            style={{
              width: 36,
              height: 36,
              borderRadius: "50%",
              background: "var(--color-primary)",
              color: "var(--color-text-on-dark)",
              border: "none",
              cursor: "pointer",
              fontSize: 13,
              fontWeight: 700,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            {initials}
          </button>

          {showDropdown && (
            <div
              style={{
                position: "absolute",
                top: 46,
                right: 0,
                background: "var(--color-surface)",
                borderRadius: "var(--radius-card)",
                boxShadow: "var(--shadow-card-hover)",
                border: "1px solid var(--color-border)",
                minWidth: 220,
                zIndex: 200,
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  padding: "16px 18px",
                  borderBottom: "1px solid var(--color-border)",
                }}
              >
                <div
                  style={{
                    fontSize: 14,
                    fontWeight: 700,
                    color: "var(--color-text-primary)",
                  }}
                >
                  {name}
                </div>
                <div
                  style={{
                    fontSize: 12,
                    color: "var(--color-text-muted)",
                    marginTop: 2,
                  }}
                >
                  {email}
                </div>
                <span
                  style={{
                    display: "inline-block",
                    marginTop: 8,
                    fontSize: 11,
                    fontWeight: 600,
                    background: "var(--color-primary)",
                    color: "var(--color-text-on-dark)",
                    padding: "3px 10px",
                    borderRadius: "var(--radius-pill)",
                  }}
                >
                  {role}
                </span>
              </div>
              <div style={{ padding: 8 }}>
                <button
                  onClick={() => signOut({ callbackUrl: "/login" })}
                  style={{
                    width: "100%",
                    padding: "10px 12px",
                    textAlign: "left",
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    fontSize: 14,
                    color: "var(--color-error-text)",
                    borderRadius: 8,
                    fontWeight: 500,
                  }}
                >
                  ← Se déconnecter
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </nav>
  )
}
