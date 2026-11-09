import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Noto Sans SC"', 'system-ui', '-apple-system', 'sans-serif'],
      },
      colors: {
        primary: {
          DEFAULT: 'var(--primary)',
          hover: 'var(--primary-hover)',
          light: 'var(--primary-light)',
          soft: 'var(--primary-soft)',
          deep: 'var(--primary-deep)',
          ink: 'var(--primary-ink)',
        },
        navy: {
          DEFAULT: 'var(--navy)',
          soft: 'var(--navy-soft)',
          text: 'var(--navy-text)',
          muted: 'var(--navy-muted)',
        },
        page: 'var(--page)',
        line: {
          DEFAULT: 'var(--line)',
          soft: 'var(--line-soft)',
        },
        field: {
          DEFAULT: 'var(--field)',
          border: 'var(--field-border)',
        },
        ink: {
          DEFAULT: 'var(--ink)',
          2: 'var(--ink-2)',
          3: 'var(--ink-3)',
        },
        muted: 'var(--muted)',
        faint: 'var(--faint)',
      },
      borderRadius: {
        card: '12px',
      },
    },
  },
  plugins: [],
} satisfies Config
