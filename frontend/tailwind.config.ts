import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#0b0f14",
        surface: "#12181f",
        border: "#1f2833",
        positive: "#22c55e",
        negative: "#ef4444",
        accent: "#3b82f6",
      },
    },
  },
  plugins: [],
};

export default config;
