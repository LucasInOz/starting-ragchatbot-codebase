# Frontend Quality Tooling Changes

## Overview

Added Prettier for automatic code formatting across the frontend, ensuring consistent style throughout all JS, CSS, and HTML files.

## Files Added

### `package.json` (project root)
- Introduces npm as the frontend tooling layer alongside `pyproject.toml` (Python/backend).
- Declares `prettier ^3.4.2` as a dev dependency.
- Provides three npm scripts:
  - `npm run format` — rewrites all frontend files in-place to match Prettier style.
  - `npm run format:check` — exits non-zero if any file is out of style (CI-safe).
  - `npm run quality` — alias for `format:check`; entry point for quality gates.

### `.prettierrc` (project root)
Prettier configuration applied to all frontend files:
- `printWidth: 100` — line length ceiling.
- `tabWidth: 2`, `useTabs: false` — 2-space soft indentation.
- `singleQuote: true` — single quotes in JS.
- `semi: true` — always include semicolons.
- `trailingComma: "es5"` — trailing commas where valid in ES5.
- `arrowParens: "always"` — `(x) => x` style.
- `endOfLine: "lf"` — Unix line endings.

### `.prettierignore` (project root)
Tells Prettier to skip `node_modules/`, `backend/`, `docs/`, and lock files so it only touches frontend assets.

### `scripts/frontend-quality.sh`
Shell script for running all frontend quality checks in one command:
```bash
bash scripts/frontend-quality.sh
```
- Auto-installs npm dependencies if `node_modules/` is missing.
- Runs `prettier --check` and reports pass/fail clearly.
- Exits with code 1 if any check fails (suitable for CI hooks).

## Files Modified

### `frontend/script.js`
- Normalized to 2-space indentation (was 4-space).
- Removed inconsistent blank lines between functions.
- Applied single-quote strings and consistent semicolons throughout.

### `frontend/style.css`
- Normalized whitespace and blank lines between rule blocks.
- Consistent spacing inside selectors and property declarations.

### `frontend/index.html`
- Normalized attribute quoting and indentation.
- Consistent 2-space indentation throughout the template.

## Usage

```bash
# Install (first time only)
npm install

# Check formatting (CI / pre-commit)
npm run format:check

# Auto-fix formatting
npm run format

# Full quality check script
bash scripts/frontend-quality.sh
```
