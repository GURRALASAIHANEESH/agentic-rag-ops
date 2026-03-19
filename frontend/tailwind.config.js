/** @type {import('tailwindcss').Config} */
const { fontFamily } = require("tailwindcss/defaultTheme");

module.exports = {
    darkMode: "class",
    content: [
        "./src/pages/**/*.{js,ts,jsx,tsx}",
        "./src/components/**/*.{js,ts,jsx,tsx}",
        "./src/app/**/*.{js,ts,jsx,tsx}",
        "./src/hooks/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                "bg-1": "#0b1020",
                "bg-2": "#0f1724",
                "bg-3": "#131d2e",
                glass: "rgba(255,255,255,0.04)",
                "glass-hover": "rgba(255,255,255,0.07)",
                "glass-border": "rgba(255,255,255,0.08)",
                "text-primary": "#e8edf3",
                "text-secondary": "#9aa4b2",
                "text-muted": "#5a6478",
                accent: {
                    DEFAULT: "#5eead4",
                    dim: "rgba(94,234,212,0.12)",
                    hover: "#4dd9c3",
                },
                warn: {
                    DEFAULT: "#f59e0b",
                    dim: "rgba(245,158,11,0.12)",
                },
                danger: {
                    DEFAULT: "#ef4444",
                    dim: "rgba(239,68,68,0.12)",
                },
                success: {
                    DEFAULT: "#22c55e",
                    dim: "rgba(34,197,94,0.12)",
                },
                border: {
                    DEFAULT: "rgba(255,255,255,0.08)",
                    subtle: "rgba(255,255,255,0.04)",
                    strong: "rgba(255,255,255,0.16)",
                },
            },
            fontFamily: {
                sans: ["var(--font-inter)", ...fontFamily.sans],
                mono: ["var(--font-mono)", "JetBrains Mono", "Fira Code", ...fontFamily.mono],
            },
            fontSize: {
                "2xs": ["0.625rem", { lineHeight: "0.875rem" }],
                xs: ["0.75rem", { lineHeight: "1rem" }],
                sm: ["0.8125rem", { lineHeight: "1.25rem" }],
                base: ["0.875rem", { lineHeight: "1.5rem" }],
                md: ["1rem", { lineHeight: "1.5rem" }],
                lg: ["1.125rem", { lineHeight: "1.75rem" }],
                xl: ["1.25rem", { lineHeight: "1.75rem" }],
                "2xl": ["1.5rem", { lineHeight: "2rem" }],
            },
            spacing: {
                sidebar: "15rem",
                panel: "22rem",
            },
            borderRadius: {
                lg: "0.75rem",
                xl: "1rem",
                "2xl": "1.25rem",
            },
            boxShadow: {
                sm: "0 1px 2px rgba(0,0,0,0.4)",
                DEFAULT: "0 2px 8px rgba(0,0,0,0.45)",
                md: "0 4px 16px rgba(0,0,0,0.5)",
                lg: "0 8px 32px rgba(0,0,0,0.6)",
                panel: "0 0 0 1px rgba(255,255,255,0.06), 0 8px 32px rgba(0,0,0,0.5)",
                "input-focus": "0 0 0 2px rgba(94,234,212,0.35)",
                glow: "0 0 20px rgba(94,234,212,0.15)",
            },
            transitionDuration: {
                fast: "80ms",
                DEFAULT: "120ms",
                medium: "200ms",
                slow: "350ms",
            },
            keyframes: {
                "fade-in": {
                    "0%": { opacity: "0", transform: "translateY(4px)" },
                    "100%": { opacity: "1", transform: "translateY(0)" },
                },
                "fade-out": {
                    "0%": { opacity: "1", transform: "translateY(0)" },
                    "100%": { opacity: "0", transform: "translateY(4px)" },
                },
                "slide-in-right": {
                    "0%": { opacity: "0", transform: "translateX(12px)" },
                    "100%": { opacity: "1", transform: "translateX(0)" },
                },
                "slide-in-left": {
                    "0%": { opacity: "0", transform: "translateX(-12px)" },
                    "100%": { opacity: "1", transform: "translateX(0)" },
                },
                shimmer: {
                    "0%": { backgroundPosition: "-200% 0" },
                    "100%": { backgroundPosition: "200% 0" },
                },
                "cursor-blink": {
                    "0%, 100%": { opacity: "1" },
                    "50%": { opacity: "0" },
                },
            },
            animation: {
                "fade-in": "fade-in 120ms cubic-bezier(0.16, 1, 0.3, 1) both",
                "fade-out": "fade-out 100ms cubic-bezier(0.16, 1, 0.3, 1) both",
                "slide-in-right": "slide-in-right 140ms cubic-bezier(0.16, 1, 0.3, 1) both",
                "slide-in-left": "slide-in-left 140ms cubic-bezier(0.16, 1, 0.3, 1) both",
                shimmer: "shimmer 2s linear infinite",
                "cursor-blink": "cursor-blink 1s step-end infinite",
            },
            backdropBlur: {
                xs: "2px",
                sm: "8px",
                md: "16px",
                lg: "24px",
            },
            gridTemplateColumns: {
                shell: "15rem 1fr",
                "shell-collapsed": "3.5rem 1fr",
                "main-split": "1fr 22rem",
            },
            zIndex: {
                base: "0",
                raised: "10",
                overlay: "20",
                modal: "30",
                toast: "40",
                tooltip: "50",
            },
        },
    },
    plugins: [
        function ({ addUtilities }) {
            addUtilities({
                ".scrollbar-hide": {
                    "-ms-overflow-style": "none",
                    "scrollbar-width": "none",
                },
                ".scrollbar-hide::-webkit-scrollbar": {
                    display: "none",
                },
                ".glass-panel": {
                    background: "rgba(15, 23, 36, 0.85)",
                    "backdrop-filter": "blur(16px)",
                    "-webkit-backdrop-filter": "blur(16px)",
                    border: "1px solid rgba(255,255,255,0.08)",
                },
                ".text-balance": {
                    "text-wrap": "balance",
                },
            });
        },
    ],
};
