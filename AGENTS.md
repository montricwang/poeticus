# Poeticus AI development conventions

These requirements apply to all AI-generated code changes and GitHub operations in this repository.

- **Commits (including squash-merge commits): English Conventional Commits**, with **type and subject required, scope optional**: `type: subject` or `type(scope): subject`. Examples: `ci: update GitHub workflows` and `fix(retrieval): reject empty tokens`. Use English for commit body and footer. Include a scope when it usefully identifies an affected module, but never invent one to satisfy formatting. Breaking changes may use `type!: subject` or `type(scope)!: subject`.
- Allowed types: `build, chore, ci, docs, feat, fix, perf, refactor, revert, style, test`.
- **PR title and PR description: Chinese** (technical names, commands, paths, and identifiers may remain English). Issue title and body: Chinese.
- **Squash and Merge:** never reuse the Chinese PR title as the Git commit title. Supply an explicit English `type: subject` or `type(scope): subject` and English commit body using GitHub's `commit_title` / `commit_message` arguments, or `gh pr merge --squash --subject ... --body ...`. Validate the final message before merge.
- The repository enforces commit formatting using `commitlint.config.mjs` and PR language using `.github/workflows/pr-language.yml`. A local opt-in commit hook lives in `.githooks/commit-msg`. GitHub administrators must separately enable required checks and commit-metadata Rulesets to prevent bypass by direct push or incorrect squash titles.
- Write PR titles and descriptions in Chinese even when all code comments or commit messages are in English.

- Frontend checks: run `npm run lint`, `npm run format:check`, `npm run build` and `npm run test:e2e` from `frontend/`; Playwright tests exercise Chromium at desktop and mobile viewports. Tailwind v4 class canonicalization is warned about in ESLint and Tailwind IntelliSense. Do not automatically rewrite or reorder established Tailwind class strings across the whole project; `npm run format:tailwind` is an explicit, opt-in migration command.
- Dependency updates arrive weekly through Dependabot; keep its PRs small. Audit Python requirements with the `Python dependency security` workflow; do not auto-fix security upgrades without tests.
