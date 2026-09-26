import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  // `landing/` is the legacy static marketing site (own index.html, firebase compat
  // scripts) — served as-is, not part of the Vite app build, so not linted with it.
  globalIgnores(['dist', 'landing']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
      parserOptions: {
        ecmaVersion: 'latest',
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    rules: {
      // Without eslint-plugin-react's jsx-uses-vars, core no-unused-vars can't see
      // <Component /> usages — ignore capitalized names for vars AND args (a
      // destructured `Icon` render prop is an arg, not a var). `motion` from
      // framer-motion is the one lowercase JSX-tag import (<motion.div>), so it's
      // allow-listed by name alongside the capitalized-name pattern.
      'no-unused-vars': ['error', { varsIgnorePattern: '^[A-Z_]|^motion$', argsIgnorePattern: '^[A-Z_]' }],
    },
  },
  {
    // Service workers (public/) run in a worker scope: `clients`, `importScripts`, etc.
    files: ['public/**/*.js'],
    languageOptions: {
      globals: { ...globals.serviceworker, ...globals.browser },
    },
  },
])
