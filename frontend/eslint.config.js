import js from '@eslint/js'
import globals from 'globals'
import tailwindcss from 'eslint-plugin-tailwindcss'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  // Tailwind v4 class suggestions; warnings avoid blocking existing styles.
  {
    files: ['**/*.{ts,tsx}'],
    plugins: { tailwindcss },
    settings: {
      tailwindcss: {
        cssConfigPath: './src/index.css',
      },
    },
    rules: {
      'tailwindcss/enforces-canonical-classname': 'warn',
      'tailwindcss/no-contradicting-classname': 'warn',
      'tailwindcss/no-unnecessary-arbitrary-value': 'warn',
    },
  },
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
  },
])
