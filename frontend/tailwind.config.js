/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        navy: {
          950: '#070b14',
          900: '#0a101d',
          850: '#0d1526',
          800: '#111a2e',
          700: '#1a2540',
          600: '#243252',
        },
        safe: '#22c55e',
        warn: '#f59e0b',
        danger: '#f97316',
        critical: '#ef4444',
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', 'Consolas', 'monospace'],
        sans: ['Inter', 'Segoe UI', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
