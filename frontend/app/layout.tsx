import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { ThemeProvider } from "@/components/theme-provider";
import { AuthProvider } from "@/lib/auth";
import { PipelineProvider } from "@/lib/pipeline-context";
import { Toaster } from "@/components/ui/sonner";
import { GalaxyStarsBackground } from "@/components/ui/galaxy-stars";
import { OmniWidget } from "@/components/omni/omni-widget";

import "./globals.css";

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
});

const jetBrainsMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Tri-Netra Forensics: AI-Powered Financial & Telecom Dataset Analyzer",
  description:
    "Tri-Netra Forensics — flagship forensic investigation platform fusing bank, CDR & IPDR intelligence with an LLM investigative co-pilot.",
  icons: { icon: "/logo.jpg" },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body className={`${inter.variable} ${jetBrainsMono.variable} font-sans antialiased bg-background text-foreground`}>
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          forcedTheme="dark"
          enableSystem={false}
          disableTransitionOnChange
        >
          <GalaxyStarsBackground
            starsCount={70}
            starsOpacity={0.42}
            glowIntensity={8}
            movementSpeed={0.14}
            mouseInfluence={55}
            gravityStrength={24}
            className="[filter:blur(3px)]"
          />
          <div className="relative z-10">
            <AuthProvider>
              <PipelineProvider>
                {children}
                <OmniWidget />
              </PipelineProvider>
            </AuthProvider>
          </div>
          <Toaster richColors position="top-right" />
        </ThemeProvider>
      </body>
    </html>
  );
}

