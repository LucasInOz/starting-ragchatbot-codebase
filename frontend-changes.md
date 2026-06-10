# Frontend Changes — Theme Toggle Button

## Feature
Added a dark/light theme toggle button positioned in the top-right corner of the UI.

## Files Modified

### `frontend/index.html`
- Added `data-theme="dark"` attribute to the `<html>` element so the CSS can scope theme variables.
- Added `#themeToggle` button element (fixed position, top-right) containing two inline SVG icons:
  - **Sun icon** (Feather-style, `class="icon-sun"`) — visible in dark mode; clicking switches to light.
  - **Moon icon** (Feather-style, `class="icon-moon"`) — visible in light mode; clicking switches to dark.
- Bumped cache-busting version query strings: `style.css?v=10`, `script.js?v=10`.

### `frontend/style.css`
- Renamed `:root` block to `:root, [data-theme="dark"]` and added explicit dark theme values.
- Added `[data-theme="light"]` block with a full light-palette override:
  - Background `#f8fafc`, surfaces white, text `#0f172a`, borders `#e2e8f0`, etc.
  - New `--code-bg`, `--toggle-bg`, `--toggle-hover-bg`, `--toggle-color`, `--toggle-hover-color` variables.
- Added smooth theme transition via `transition: background-color 0.3s ease, color 0.3s ease, border-color 0.3s ease, box-shadow 0.3s ease` on all theme-sensitive elements (body, sidebar, messages, inputs, etc.).
- Replaced hardcoded `rgba(0, 0, 0, 0.2)` code-block backgrounds with `var(--code-bg)` so they adapt to both themes.
- Added `.theme-toggle` styles:
  - `position: fixed; top: 1rem; right: 1rem; z-index: 1000`
  - 40×40 px circular button with rounded border and theme-variable colours.
  - Hover: subtle scale-up + shadow.
  - Focus: `:focus-visible` ring using `--focus-ring`.
  - Active: slight scale-down press effect.
- Icon visibility rules: `[data-theme="dark"]` hides moon / shows sun; `[data-theme="light"]` hides sun / shows moon.
- Added `.theme-toggle.animating svg` keyframe (`icon-spin`) for a brief spin-in animation on each toggle.

### `frontend/script.js`
- Added `themeToggle` to the DOM element declarations.
- Added `initTheme()` — reads `localStorage.getItem('theme')` (defaults to `'dark'`) and calls `applyTheme()` on load.
- Added `applyTheme(theme, animate)` — sets `data-theme` on `<html>`, updates `aria-label` / `title` for accessibility, and optionally triggers the spin animation.
- Added `toggleTheme()` — flips between `'dark'` and `'light'`, persists choice to `localStorage`, calls `applyTheme()` with animation.
- Wired `themeToggle.addEventListener('click', toggleTheme)` in `setupEventListeners()`.

## Accessibility
- `aria-label` is updated dynamically to always describe the *action* ("Switch to light mode" / "Switch to dark mode").
- Both SVG icons carry `aria-hidden="true"` so screen readers rely on the button's label only.
- Focus indicator uses `:focus-visible` with `--focus-ring` outline (matches existing send-button style).
- Button is fully keyboard-navigable (native `<button>` element, no `tabindex` hacks needed).

## Behaviour
- Theme preference persists across page reloads via `localStorage`.
- All colour transitions animate smoothly in 300 ms.
- Icon switches with a brief spin-in animation (400 ms) on each toggle.

---

# Frontend Changes — Light Theme Refinement & Accessibility Audit

## Feature
Audited and completed the light theme so every component meets WCAG AA contrast requirements and no element relies on a hardcoded colour that breaks in light mode.

## Files Modified

### `frontend/style.css`

#### Dark theme (`[data-theme="dark"]`) — new variables added
| Variable | Value | Purpose |
|---|---|---|
| `--welcome-shadow` | `0 4px 16px rgba(0,0,0,0.25)` | Welcome-banner drop shadow |
| `--error-bg/text/border` | `rgba(239,68,68,.1)` / `#f87171` / `rgba(239,68,68,.25)` | Error state colours |
| `--success-bg/text/border` | `rgba(34,197,94,.1)` / `#4ade80` / `rgba(34,197,94,.25)` | Success state colours |
| `--link-hover-color` | `#ffffff` | `.sources-content a:hover` |

#### Light theme (`[data-theme="light"]`) — full colour audit
All values checked against WCAG AA (4.5:1 normal text, 3:1 large/UI text):

| Variable | Value | Contrast vs surface | Notes |
|---|---|---|---|
| `--primary-color` | `#1d4ed8` | 5.9:1 on white | Deepened from `#2563eb` for better contrast on light surfaces |
| `--primary-hover` | `#1e40af` | — | Darker on hover |
| `--text-primary` | `#0f172a` | ~19:1 on white | Near-black — excellent |
| `--text-secondary` | `#475569` | 5.5:1 on white | Passes AA; was `#64748b` (4.86:1 — borderline) |
| `--border-color` | `#cbd5e1` | — | Slightly darker than `#e2e8f0` for crisper borders |
| `--welcome-border` | `#93c5fd` | — | Soft blue — complements `--welcome-bg: #eff6ff` |
| `--welcome-shadow` | `0 4px 16px rgba(0,0,0,.06)` | — | Subtle shadow on light background |
| `--error-text` | `#b91c1c` | 6.0:1 on white | Accessible dark red |
| `--success-text` | `#15803d` | 5.1:1 on white | Accessible dark green |
| `--link-hover-color` | `#1e3a8a` | — | Dark navy — visible on any light surface |
| `--code-bg` | `rgba(15,23,42,.06)` | — | Dark tint on white for code blocks |
| `--user-message` | `#1d4ed8` | — | Matches `--primary-color`; white text = 5.9:1 |

#### Bug fixes
- **`.sources-content a:hover`**: was hardcoded `color: #fff` (invisible on light backgrounds) → now `color: var(--link-hover-color)`.
- **`.message-content blockquote`**: was `border-left: 3px solid var(--primary)` — `--primary` was never defined → fixed to `var(--primary-color)`.

#### Semantically corrected rules
- **`.message.welcome-message .message-content`**: `background`, `border`, and `box-shadow` now use `--welcome-bg`, `--welcome-border`, and `--welcome-shadow` (were partially hardcoded).
- **`.error-message`** and **`.success-message`**: all three colour properties (`background`, `color`, `border`) now use the `--error-*` / `--success-*` variables; added `transition` so they animate on theme switch.
- **`.message.user .message-content`**: added `transition: background-color 0.3s ease` for smooth bubble colour change on toggle.
- **`.message-content blockquote`**: added `transition` for border and text colour.
