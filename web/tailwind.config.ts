import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Decision-tier palette, reused by the console in Phase 8.
        allow: "#2f8f5b",
        edit: "#b3771a",
        review: "#3a6ea8",
        block: "#c0392f",
      },
    },
  },
  plugins: [],
};

export default config;
