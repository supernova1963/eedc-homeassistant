/* eslint-env node */
module.exports = {
  root: true,
  env: { browser: true, es2020: true, node: true },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
  ],
  ignorePatterns: ['dist', 'node_modules', '.eslintrc.cjs'],
  parser: '@typescript-eslint/parser',
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
  },
  plugins: ['react-refresh', '@typescript-eslint'],
  rules: {
    // react-refresh/only-export-components — BEWUSST AUS (Gernot 2026-07-16).
    //
    // Die Regel verlangt, dass eine Datei NUR Komponenten exportiert. eedc nutzt
    // aber bewusst das `*Teile.tsx`-Muster: eine Datei bündelt die Komponenten
    // eines Bereichs MIT ihren Hooks/Helfern (`useInvestitionenVerwaltung`,
    // `sucheEintraege`, …) und wird von V3 und V4 gemeinsam genutzt — genau der
    // Konvergenz-Gedanke „eine Code-Wahrheit, nie zwei Kopien". Die Regel kennt
    // dieses Muster nicht; sie kollidiert damit strukturell.
    //
    // Sie hat KEINE Laufzeitwirkung — betroffen ist allein der Fast-Refresh-Komfort
    // beim Entwickeln (Datei-Edit = volles Reload statt State-Erhalt). Der billige
    // Ausweg war ausgereizt: `allowConstantExport` deckte nur Konstanten-Exports,
    // 67 der 82 Meldungen waren Funktions-Exports. Der Rest hieße ~50 Dateien
    // aufspalten (Import-Churn quer durchs Repo, mitten im IA-V4-Restweg) — Kosten
    // ohne jeden Nutzereffekt. Entscheidung: das Muster bleibt, die Regel geht.
    //
    // Effekt: 101 → 19 Warnungen. Die verbliebenen sind `react-hooks/exhaustive-deps`
    // = echte Bug-Klasse (belegt: eingefrorener Aufklapp-Zustand durch fehlende
    // useMemo-Dep) und damit wieder echtes Signal statt Rauschen.
    'react-refresh/only-export-components': 'off',
    '@typescript-eslint/no-unused-vars': [
      'error',
      {
        argsIgnorePattern: '^_',
        varsIgnorePattern: '^_',
        caughtErrorsIgnorePattern: '^_',
        destructuredArrayIgnorePattern: '^_',
      },
    ],
    'no-unused-vars': 'off',
  },
}
