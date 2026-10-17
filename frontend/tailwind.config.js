/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        pine: {
          DEFAULT: "#0b2420",
          mid: "#143832",
          soft: "#1e4a42",
        },
        copper: {
          DEFAULT: "#c46b2d",
          deep: "#9a5222",
          soft: "#f3e0d2",
        },
        moss: {
          DEFAULT: "#1a7a6d",
          soft: "#d8ebe7",
        },
        stone: "#e8ece9",
        paper: "#f7f8f6",
        ink: "#14201c",
        mute: "#5c6b64",
        accent: "#c46b2d",
        sidebar: "#0b2420",
      },
      fontFamily: {
        display: ['"Fraunces"', "Georgia", "serif"],
        body: ['"Figtree"', "system-ui", "sans-serif"],
      },
      boxShadow: {
        lift: "0 1px 0 rgba(20,32,28,0.06), 0 8px 24px rgba(11,36,32,0.06)",
        soft: "0 1px 0 rgba(20,32,28,0.05)",
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
