/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: '#09090b',
        card: '#18181b',
        border: '#27272a',
        accent: '#eab308',
        'accent-hover': '#ca8a04',
        muted: '#a1a1aa',
        spotify: '#1DB954',
        brand: {
          dark: '#09090b',
          card: '#18181b',
          border: '#27272a',
          gold: '#fbbf24',
          goldHover: '#f59e0b',
        }
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        display: ['"Plus Jakarta Sans"', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      }
    },
  },
  plugins: [],
}
