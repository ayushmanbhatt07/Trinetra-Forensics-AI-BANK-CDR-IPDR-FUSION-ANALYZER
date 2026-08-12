"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/lib/auth"

export default function AppLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const { ready, user } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (ready && !user) router.replace("/login")
  }, [ready, user, router])

  if (!ready || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 rounded-full border-2 border-emerald-500/30 border-t-emerald-500 animate-spin" />
          <p className="text-sm text-muted-foreground font-mono animate-pulse">
            AUTHENTICATING...
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Main Content */}
      <main className="flex-1 flex flex-col h-full overflow-hidden relative">
        <div className="flex-1 overflow-y-auto">
          {children}
        </div>
      </main>
    </div>
  )
}
