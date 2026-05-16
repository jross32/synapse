import type { Config } from 'tailwindcss';
import animate from 'tailwindcss-animate';

// Tailwind + shadcn/ui colour system. The HSL channel values live as CSS
// variables in renderer/styles.css; this config maps them to utility names.
// Synapse's own brand tokens (theme-tokens.css, --synapse-*) still exist for
// anything outside the shadcn component set.
const config: Config = {
  darkMode: ['class'],
  content: [
    './renderer/index.html',
    './renderer/**/*.{ts,tsx}',
    './mobile/**/*.{ts,tsx,html}',
  ],
  theme: {
    extend: {
      colors: {
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))',
        },
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
        // Synapse status palette — used by StatusBadge etc.
        status: {
          idle: 'hsl(var(--status-idle))',
          launching: 'hsl(var(--status-launching))',
          launched: 'hsl(var(--status-launched))',
          stopping: 'hsl(var(--status-stopping))',
          stopped: 'hsl(var(--status-stopped))',
          error: 'hsl(var(--status-error))',
        },
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        mono: ['JetBrains Mono', 'Cascadia Code', 'Consolas', 'monospace'],
      },
      keyframes: {
        'synapse-pulse': {
          '0%, 100%': { opacity: '1', transform: 'scale(1)' },
          '50%': { opacity: '0.4', transform: 'scale(0.85)' },
        },
      },
      animation: {
        'synapse-pulse': 'synapse-pulse 1.2s ease-in-out infinite',
      },
    },
  },
  plugins: [animate],
};

export default config;
