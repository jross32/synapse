import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './renderer/index.html',
    './renderer/**/*.{ts,tsx}',
    './mobile/**/*.{ts,tsx,html}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Synapse neural palette — finalised in Milestone F
        nucleus: {
          DEFAULT: '#0f172a',
          accent: '#7c3aed',
        },
        synapse: {
          DEFAULT: '#1e293b',
          glow: '#22d3ee',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};

export default config;
