"use client";

/**
 * Copy Button (Animate UI blend) — copies content to the clipboard and
 * swaps the icon to a checkmark with a spring pop.
 */
import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export function CopyButton({
  content,
  label = "Copy",
  copiedLabel = "Copied",
  delay = 3000,
  className,
  variant = "ghost",
}: {
  content: string;
  label?: string;
  copiedLabel?: string;
  delay?: number;
  className?: string;
  variant?: "default" | "outline" | "ghost" | "secondary";
}) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(content);
      } else {
        const ta = document.createElement("textarea");
        ta.value = content;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        ta.remove();
      }
      setCopied(true);
      window.setTimeout(() => setCopied(false), delay);
    } catch {
      /* clipboard unavailable */
    }
  };

  const variantCls =
    variant === "outline"
      ? "border bg-background hover:bg-accent hover:text-accent-foreground"
      : variant === "secondary"
        ? "bg-secondary text-secondary-foreground hover:bg-secondary/80"
        : "hover:bg-muted hover:text-foreground";

  return (
    <motion.button
      onClick={copy}
      type="button"
      title={copied ? copiedLabel : label}
      aria-label={copied ? copiedLabel : label}
      whileTap={{ scale: 0.92 }}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium",
        "text-muted-foreground transition-colors duration-200",
        variantCls,
        className
      )}
    >
      <motion.span
        key={copied ? "check" : "copy"}
        initial={{ scale: 0.4, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", stiffness: 500, damping: 22 }}
        className="grid place-items-center"
      >
        {copied ? (
          <Check className="size-3.5 text-emerald-400" />
        ) : (
          <Copy className="size-3.5" />
        )}
      </motion.span>
      {copied ? copiedLabel : label}
    </motion.button>
  );
}
