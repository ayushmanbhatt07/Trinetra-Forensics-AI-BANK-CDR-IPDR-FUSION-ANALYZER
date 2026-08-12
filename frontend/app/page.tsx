"use client"

import { useState, useEffect } from "react"
import { motion, AnimatePresence } from "framer-motion"
import MatrixRainEnhanced from "@/components/ui/matrix-rain"
import { HeroSection } from "@/components/ui/hero-section"

export default function LandingPage() {
  const [stage, setStage] = useState<"matrix" | "hero">("matrix")

  useEffect(() => {
    if (stage === "matrix") {
      const timer = setTimeout(() => setStage("hero"), 4000)
      return () => clearTimeout(timer)
    }
  }, [stage])

  return (
    <main className="relative min-h-screen bg-black text-foreground overflow-hidden">
      <AnimatePresence mode="wait">
        {stage === "matrix" && (
          <motion.div
            key="matrix"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, filter: "blur(10px)" }}
            transition={{ duration: 1.2, ease: "easeInOut" }}
            className="absolute inset-0 z-50 bg-black"
          >
            <MatrixRainEnhanced />
            <div className="absolute inset-x-0 bottom-10 flex justify-center z-50">
              <button 
                onClick={() => setStage("hero")}
                className="text-emerald-500/50 hover:text-emerald-400 font-mono text-sm tracking-widest transition-colors bg-black/50 px-4 py-2 rounded-full border border-emerald-900/50"
              >
                [ SKIP SEQUENCE ]
              </button>
            </div>
          </motion.div>
        )}

        {stage === "hero" && (
          <motion.div
            key="hero"
            initial={{ opacity: 0, scale: 1.05 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 1.5, ease: "easeOut" }}
            className="absolute inset-0 z-10"
          >
            <HeroSection />
          </motion.div>
        )}
      </AnimatePresence>
    </main>
  )
}
