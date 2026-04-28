/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        mvx: {
          bg:           '#181f25',
          surface:      '#202a32',
          border:       '#28343e',
          muted:        '#8B9CA9',
          accent:       '#956fff',
          'accent-hover': '#7c5ee0',
          signal:       '#74dc93',
          danger:       '#ff5447',
        },
      },
      fontFamily: {
        sans:    ['"DM Sans"', 'sans-serif'],
        display: ['"Clash Display"', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
