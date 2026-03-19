import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import clsx from "clsx";
import "@/app/globals.css";
import { Providers } from "@/app/providers";

// ── Font loading ──────────────────────────────────────────────────────────────
// Variable fonts loaded via Next.js font optimization — zero layout shift.

const inter = Inter({
    subsets: ["latin"],
    display: "swap",
    variable: "--font-inter",
    weight: ["400", "500", "600", "700"],
});

const jetbrainsMono = JetBrains_Mono({
    subsets: ["latin"],
    display: "swap",
    variable: "--font-mono",
    weight: ["400", "500"],
});

// ── Metadata ──────────────────────────────────────────────────────────────────

export const metadata: Metadata = {
    title: {
        template: "%s | RAG Ops",
        default: "RAG Ops — Agentic Retrieval Platform",
    },
    description:
        "Production-grade agentic RAG system with streaming responses, critic verification, and full document provenance.",
    robots: { index: false, follow: false },
    icons: {
        icon: "/favicon.ico",
        shortcut: "/favicon-16x16.png",
        apple: "/apple-touch-icon.png",
    },
};

export const viewport: Viewport = {
    themeColor: "#0b1020",
    colorScheme: "dark",
    width: "device-width",
    initialScale: 1,
};

// ── Root layout ───────────────────────────────────────────────────────────────

export default function RootLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return (
        <html
            lang="en"
            className={clsx(
                "dark",
                inter.variable,
                jetbrainsMono.variable
            )}
            suppressHydrationWarning
        >
            <body
                className={clsx(
                    "min-h-screen bg-bg-1 font-sans text-text-primary antialiased",
                    "selection:bg-accent/20 selection:text-accent"
                )}
            >
                <Providers>{children}</Providers>
            </body>
        </html>
    );
}
