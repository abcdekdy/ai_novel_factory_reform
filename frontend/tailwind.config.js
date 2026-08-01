/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Apple 设计系统
        'apple-blue': '#007AFF',
        'apple-blue-hover': '#0062CC',
        'apple-blue-dim': '#E5F0FF',
        'apple-bg': '#F5F5F7',
        'apple-sidebar': '#EDEDF0',
        'apple-card': '#FFFFFF',
        'apple-text': '#1D1D1F',
        'apple-text-secondary': '#6E6E73',
        'apple-text-muted': '#8E8E93',
        'apple-border': '#D2D2D7',
        'apple-success': '#34C759',
        'apple-warning': '#FF9500',
        'apple-error': '#FF3B30',
      },
      fontFamily: {
        system: [
          'SF Pro Display',
          'SF Pro Text',
          'Inter',
          'Segoe UI',
          'PingFang SC',
          'Microsoft YaHei',
          'sans-serif',
        ],
      },
      borderRadius: {
        'apple-sm': '4px',
        'apple': '8px',
        'apple-md': '10px',
        'apple-lg': '14px',
        'apple-xl': '20px',
        'apple-full': '999px',
      },
      boxShadow: {
        'apple': '0 2px 12px rgba(0, 0, 0, 0.06)',
        'apple-lg': '0 8px 32px rgba(0, 0, 0, 0.08)',
        'apple-card': '0 1px 3px rgba(0, 0, 0, 0.04), 0 4px 12px rgba(0, 0, 0, 0.06)',
      },
      backdropBlur: {
        'glass': '20px',
        'glass-heavy': '40px',
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'slide-in-right': 'slideInRight 0.3s ease-out',
        'scale-in': 'scaleIn 0.2s ease-out',
        'pulse-soft': 'pulseSoft 2s ease-in-out infinite',
        'shimmer': 'shimmer 2s linear infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideInRight: {
          '0%': { opacity: '0', transform: 'translateX(16px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        scaleIn: {
          '0%': { opacity: '0', transform: 'scale(0.95)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        pulseSoft: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.6' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
    },
  },
  plugins: [],
}
