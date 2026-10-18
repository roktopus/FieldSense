/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        pine: {
          DEFAULT: "#100e0c",
          mid: "#1c1916",
          soft: "#2a241e",
        },
        copper: {
          DEFAULT: "#f4f1ec",
          deep: "#d8d2c8",
          soft: "#2a241e",
        },
        moss: {
          DEFAULT: "#d8d2c8",
          soft: "#1c2420",
        },
        stone: "#14110e",
        paper: "#1e1a16",
        ink: "#f6f3ee",
        mute: "#c2b8ac",
        accent: "#0a0a0a",
        sidebar: "#0a0a0a",
      },
      fontFamily: {
        display: ['"Figtree"', "system-ui", "sans-serif"],
        body: ['"Figtree"', "system-ui", "sans-serif"],
      },
      boxShadow: {
        lift: "none",
        soft: "none",
      },
      keyframes: {
        "fs-enter": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fs-enter": "fs-enter 160ms ease-out",
      },
    },
  },
  plugins: [],
};
