"use client"

import { useState, useEffect, useCallback } from "react"
import { usePathname, useRouter } from "next/navigation"
import { useAuth } from "@/lib/auth"
import { Sidebar } from "@/components/dashboard/sidebar"
import { Header } from "@/components/dashboard/header"
import { TransactionSTRReport } from "@/components/omni/transaction-str"
import { usePipeline } from "@/lib/pipeline-context"

export default function AppLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const { ready, user } = useAuth()
  const router = useRouter()
  const pathname = usePathname()

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [strTransactionId, setStrTransactionId] = useState<string | null>(null)
  const [showIngestPrompt, setShowIngestPrompt] = useState(false)

  const { isFusedReady, pipeline, loading: pipelineLoading } = usePipeline()

  // Derive active section from pathname
  const activeSection = (pathname.split("/")[1] || "dashboard") as any

  const handleCloseStr = useCallback(() => {
    setStrTransactionId(null)
  }, [])

  const handleOpenIngestion = useCallback(() => {
    router.push("/ingestion")
    setShowIngestPrompt(false)
  }, [router])

  useEffect(() => {
    if (ready && !user) router.replace("/login")
  }, [ready, user, router])

  useEffect(() => {
    const handleStr = (e: Event) => {
      const customEvent = e as CustomEvent<string>
      if (customEvent.detail) {
        setStrTransactionId(customEvent.detail)
      }
    }

    const handleApi409 = () => {
      if (!isFusedReady && !pipeline?.dataset_id) {
        setShowIngestPrompt(true)
      }
    }

    window.addEventListener("pdf:transaction", handleStr)
    window.addEventListener("api:409", handleApi409)
    return () => {
      window.removeEventListener("pdf:transaction", handleStr)
      window.removeEventListener("api:409", handleApi409)
    }
  }, [isFusedReady, pipeline?.dataset_id])

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
    <div className="flex min-h-screen bg-background">
      <Sidebar
        activeSection={activeSection}
        onSectionChange={(section) => router.push(`/${section}`)}
        collapsed={sidebarCollapsed}
        onCollapsedChange={setSidebarCollapsed}
      />
      <div
        className={`flex-1 flex flex-col h-screen overflow-hidden transition-all duration-300 ease-out ${
          sidebarCollapsed ? "ml-[72px]" : "ml-[260px]"
        }`}
      >
        <Header activeSection={activeSection} />
        <main className="flex-1 p-6 overflow-auto relative">
          {children}
        </main>
      </div>

      {strTransactionId && (
        <TransactionSTRReport 
          transactionId={strTransactionId} 
          onClose={handleCloseStr} 
        />
      )}

      {showIngestPrompt && !isFusedReady && !pipeline?.dataset_id && !pipelineLoading && activeSection !== "ingestion" && (
        <div className="fixed inset-0 z-[100] flex flex-col items-center justify-center overflow-hidden">
          {/* Background Image with 10-20% blur */}
          <div 
            className="absolute inset-0 scale-105 bg-cover bg-center bg-no-repeat blur-[4px]"
            style={{ backgroundImage: "url('/logo.jpg')" }}
          />
          {/* Dark overlay to ensure text readability */}
          <div className="absolute inset-0 bg-background/70" />
          
          <div className="relative z-10 flex flex-col items-center space-y-6">
            <h2 className="text-2xl font-bold tracking-widest text-emerald-400 drop-shadow-[0_0_8px_rgba(52,211,153,0.8)]">
              NO DATA LOADED
            </h2>
            <button
              onClick={handleOpenIngestion}
              className="group relative overflow-hidden rounded-full border border-emerald-500/50 bg-emerald-950/40 px-10 py-4 font-mono font-bold text-emerald-400 shadow-[0_0_20px_rgba(52,211,153,0.3)] transition-all hover:scale-105 hover:bg-emerald-900/50 hover:shadow-[0_0_30px_rgba(52,211,153,0.6)]"
            >
              <div className="absolute inset-0 -translate-x-full animate-[shimmer_2s_infinite] bg-gradient-to-r from-transparent via-emerald-400/10 to-transparent"></div>
              Upload / Ingest Data Now
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
