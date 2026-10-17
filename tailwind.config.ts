import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Core semantic palette
        canvas: "#FFF8E7",
        paper: {
          DEFAULT: "#FFF8E7",
          dark: "#F5ECD6",
          light: "#FFF8E7",
          parchment: "#EFE4C8",
        },
        ink: {
          DEFAULT: "#141414",
          muted: "#3F3F3F",
          faint: "#6B6B6B",
          border: "#141414",
        },
        primary: {
          DEFAULT: "#FFD12E",
          hover: "#F5C400",
        },
        sunburst: "#FFD12E",
        berry: "#FF3E8A",
        mint: "#00E5A3",
        // Secondary colors strictly for skill badges, blast particles, and hero letter tiles
        tomato: {
          DEFAULT: "#FF4F2E",
          hover: "#E03C1C",
        },
        sky: "#38BDF8",
        lime: "#A3E635",
        violet: "#8B5CF6",
        pop: {
          yellow: "#FFD12E",
          mint: "#00E5A3",
          sky: "#38BDF8",
          berry: "#FF3E8A",
          lime: "#A3E635",
          tomato: "#FF4F2E",
          violet: "#8B5CF6",
        },
        editorial: {
          red: "#FF3E8A",
          "red-bg": "rgba(255, 62, 138, 0.14)",
          amber: "#FFD12E",
          "amber-bg": "rgba(255, 209, 46, 0.22)",
          green: "#00E5A3",
          "green-bg": "rgba(0, 229, 163, 0.18)",
        },
      },
      fontFamily: {
        headline: ["var(--font-space-grotesk)", "system-ui", "sans-serif"],
        body: ["var(--font-inter)", "system-ui", "sans-serif"],
        mono: ["var(--font-jetbrains-mono)", "monospace"],
      },
      boxShadow: {
        ink: "4px 4px 0px #141414",
        "ink-sm": "4px 4px 0px #141414",
        "ink-lg": "4px 4px 0px #141414",
        "ink-xl": "4px 4px 0px #141414",
        "ink-hover": "2px 2px 0px #141414",
        none: "0 0 0 transparent",
      },
      borderWidth: {
        DEFAULT: "3px",
        "2": "3px",
        "3": "3px",
      },
      borderRadius: {
        neo: "8px",
      },
    },
  },
  plugins: [],
};

export default config;
