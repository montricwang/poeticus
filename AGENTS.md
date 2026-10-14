# Poeticus AI development conventions

These requirements apply to all AI-generated code changes and GitHub operations in this repository.

- **Commits (including squash-merge commits): English Conventional Commits**, with **both type and scope mandatory**: `type(scope): subject`. Example: `fix(retrieval): reject empty tokens`. Use English for commit body and footer. Do not omit the scope even for docs, CI, or housekeeping. Breaking changes may use `type(scope)!: subject`.
- Allowed types: `build, chore, ci, docs, feat, fix, perf, refactor, revert, style, test`.
- **PR title and PR description: Chinese** (technical names, commands, paths, and identifiers may remain English). Issue title and body: Chinese.
- **Squash and Merge:** never reuse the Chinese PR title as the Git commit title. Supply an explicit English `type(scope): subject` and English commit body using GitHub's `commit_title` / `commit_message` arguments, or `gh pr merge --squash --subject ... --body ...`. Validate the final message before merge.
- The repository enforces commit formatting using `commitlint.config.mjs` and PR language using `.github/workflows/pr-language.yml`. A local opt-in commit hook lives in `.githooks/commit-msg`. GitHub administrators must separately enable required checks and commit-metadata Rulesets to prevent bypass by direct push or incorrect squash titles.
- Write PR titles and descriptions in Chinese even when all code comments or commit messages are in English.
