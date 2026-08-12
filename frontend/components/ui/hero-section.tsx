"use client"

import { useRouter } from "next/navigation"
import Link from "next/link"
import Image from "next/image"
import { ArrowRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Shader,
  Ascii,
  CursorTrail,
  Godrays,
  RadialGradient,
  Tritone
} from 'shaders/react'

export function HeroSection() {
  const router = useRouter()
  return (
    <>
      {/* Fixed Shader Background */}
      <div 
        className="fixed inset-0 -z-10"
        aria-hidden="true"
      >
        <Shader className="absolute inset-0">
          <RadialGradient
            center={{ x: 0.83, y: 0.2 }}
            colorA="#030d2b"
            colorB="#010f14"
            colorSpace="linear"
            radius={1.37} 
          />
          <Ascii
            cellSize={30}
            characters="||||"
            fontFamily="Space Mono"
            spacing={1}
          >
            <Godrays
              backgroundColor="#b59318"
              center={{ x: 0.85, y: 0.15 }}
              density={0.2}
              intensity={0.55}
              rayColor="#fcfeff"
              speed={0.6}
              spotty={0.6} 
            />
            <CursorTrail
              colorA="#ffffff"
              colorB="#000000"
              colorSpace="linear"
              length={0.45}
              radius={0.28}
              shrink={4} />
            <Tritone
              blendMid={0.73}
              colorA="#070b1f"
              colorB="#2600ff"
              colorC="#ffee03"
              colorSpace="linear"
              visible={true} 
            />
          </Ascii>
        </Shader>
      </div>

      {/* Hero Content */}
      <section className="relative min-h-screen flex flex-col">
        {/* Navigation */}
        <nav className="flex items-center justify-between p-6 md:p-10">
          <div className="flex items-center gap-6">
            <Link
              href="/"
              title="Tri-Netra Forensics — home"
              aria-label="Tri-Netra Forensics home"
              className="transition-transform duration-200 hover:scale-105"
            >
              <Image
                src="/logo.jpg"
                alt=""
                width={40}
                height={40}
                className="size-10 rounded-xl border border-cyan-500/30 object-cover shadow-lg shadow-cyan-950/40 ring-1 ring-cyan-500/20"
              />
            </Link>
          </div>
        </nav>

        {/* Main Hero Content */}
        <div className="flex-1 flex flex-col justify-center px-6 md:px-10 pb-16 pt-4">
          <div className="max-w-6xl z-10">
            {/* Oversized Typography */}
            <h1 
              className="text-[clamp(2.1rem,7.2vw,7.2rem)] font-bold leading-[0.9] tracking-[-0.03em] text-foreground font-[family-name:var(--font-sans)]"
            >
              <span className="block">TRI-NETRA FORENSICS</span>
              <span className="block">AI-Powered Financial & Telecom</span>
              <span className="block text-emerald-500 font-mono tracking-tighter">[DATASET ANALYZER]</span>
            </h1>

            {/* Tagline with accent */}
            <div className="mt-6 md:mt-8 flex flex-col md:flex-row md:items-end gap-6 md:gap-12">
              <p className="text-lg md:text-xl text-muted-foreground max-w-md leading-relaxed">
                Next-generation intelligence platform correlating financial trails and telecom data to uncover hidden networks.
              </p>
              
              <button
                onClick={() => router.push("/dashboard")}
                className="group relative flex flex-col items-center gap-3 py-6 px-10 rounded-3xl border border-emerald-500/50 bg-black/60 backdrop-blur-xl transition-all duration-500 hover:scale-105 hover:border-emerald-400 hover:shadow-[0_0_80px_-15px_rgba(16,185,129,0.5)]"
              >
                <div className="absolute inset-0 rounded-3xl bg-emerald-500/5 blur-xl group-hover:bg-emerald-500/10 transition-colors" />
                
                <div className="relative p-3.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 group-hover:bg-emerald-500/20 group-hover:border-emerald-400 transition-colors">
                  <ArrowRight className="w-6 h-6 text-emerald-500" />
                </div>
                
                <div className="relative text-center font-mono">
                  <h2 className="text-lg font-bold text-emerald-500 tracking-widest mb-1 drop-shadow-[0_0_10px_rgba(16,185,129,0.5)]">
                    UPLOAD & INGEST DATA
                  </h2>
                  <p className="text-emerald-500/70 text-xs">
                    Initialize Forensics Pipeline
                  </p>
                </div>
              </button>
            </div>
          </div>
        </div>

        {/* Bottom Bar */}
        <div className="absolute bottom-0 left-0 right-0 flex items-center justify-between p-6 md:p-10 border-t border-border/50 bg-black/50 backdrop-blur-md z-10">
          <div className="flex items-center gap-4">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="font-mono text-sm text-emerald-500/80 tracking-widest">SYSTEM ONLINE</span>
          </div>
          <span className="font-mono text-sm text-muted-foreground">v2.0.0-rc1</span>
        </div>
      </section>
    </>
  )
}
