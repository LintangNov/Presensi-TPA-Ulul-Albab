# Design System — Absensi TPA

## Design Direction & Vision

The Absensi TPA interface is designed for a dual-context use case: **admin management** on desktop and **public TV LED display** for real-time attendance feedback. The visual language prioritizes **clarity, legibility at distance, and calm professionalism** suitable for an Islamic school environment.

The palette centers on **aquamarine and sky blue** tones rather than generic tech blues, creating a distinctive, approachable identity. Components favor **functional simplicity** over decoration—shadows are minimal, borders are crisp, and interactive states are obvious. The design assumes Windows PC deployment with Edge browser and USB RFID reader hardware.

---

## Color System

### Core Palette

```css
--aquamarine: #a5ffd6;      /* Success, attendance confirmed */
--grey-olive: #817f75;       /* Reserved neutral */
--pale-slate: #b3b5bb;       /* Border default */
--pale-sky: #c5d9e2;         /* Sidebar, info states */
--frozen-water: #cdfff9;     /* Accent hover/highlight */
```

### Semantic Tokens

```css
--bg: #eefcfa;               /* Page background (light aqua tint) */
--surface: #ffffff;          /* Cards, panels, elevated surfaces */
--sidebar: #c5d9e2;          /* Left navigation background */
--primary: #3283e7;          /* Primary action blue */
--primary-soft: #859fd0;     /* Soft primary for hover/secondary */
--border: #b3b5bb;           /* Default border color */
--text: #2b2a26;             /* Primary text (dark warm gray) */
--text-muted: #5f5d55;       /* Secondary text */
--focus: #2b2a26;            /* Focus ring color */
```

### Status Colors

```css
--success: #a5ffd6;          /* Attendance success, active status */
--warning: #fff0b8;          /* Warning states, duplicate tap */
--error: #ff6b6b;            /* Error, penalty (denda) */
--info: #c5d9e2;             /* Informational, picked up status */
--inactive: #ffd0a8;         /* Inactive student, disabled state */
```

### Usage Guidelines

- **Backgrounds:** Use `--bg` (#eefcfa) for body, `--surface` (#ffffff) for elevated cards. The aqua tint differentiates surface from background without harshness.
- **Text:** `--text` (#2b2a26) for primary content, `--text-muted` (#5f5d55) for labels and secondary info. Avoid pure black (#000000).
- **Borders:** Use `--border` (#b3b5bb) universally. Avoid multiple border color variants unless semantically necessary.
- **Status feedback:** Map attendance results to semantic colors consistently. "Berhasil" = `--success`, "Denda" = `--error`, "Sudah absen" = `--warning`.

### Contrast Requirements

- All text on `--surface` (#ffffff) meets WCAG AA with `--text` (#2b2a26).
- Status badges use high-contrast background/foreground pairings.
- TV display mode uses larger text (clamp minimum 0.95rem) for distance legibility.

---

## Typography

### Font Stack

```css
--font-body: system-ui, -apple-system, "Segoe UI", sans-serif;
```

All text uses the system font stack for native rendering on Windows (Segoe UI primary). No custom web fonts—ensures instant load and optimal ClearType rendering.

### Scale & Hierarchy

**Admin Interface:**
```css
h1: 2.2rem (35.2px)         /* Page titles */
h2: 1.4rem (22.4px)         /* Section headers */
h3: 1.35rem (21.6px)        /* Sidebar brand, subsections */
body: 1rem (16px)           /* Base text, line-height 1.55 */
small: 0.85rem (13.6px)     /* Metadata, captions */
code: 0.9rem (14.4px)       /* RFID UIDs, technical data */
```

**TV Display Mode (Responsive):**
```css
h1: clamp(1.5rem, 3.5vw, 2.3rem)    /* Main status heading */
h2: clamp(1.2rem, 2.5vw, 1.8rem)    /* Header brand */
body: clamp(0.95rem, 1.6vw, 1.2rem) /* Descriptive text */
time: clamp(1rem, 2vw, 1.4rem)      /* Clock display */
```

### Weight & Style

- **Regular (400):** Body text, form labels
- **Semi-bold (600):** Badges, pagination info, metadata
- **Bold (700):** Buttons, navigation links, table headers, emphasis
- **Extra-bold (800):** TV display headings, status badges

### Line Height

- **Body text:** 1.55 (optimal readability for paragraphs)
- **Headings:** Inherit or 1.2 (tighter for large text)
- **Buttons/UI:** 1 (centered single-line labels)


## Layout & Geometry

### Grid & Spacing

**Sidebar Layout:**
- Sidebar: 250px fixed width, `--sidebar` background
- Main content: `flex: 1` with `padding: 2rem 2.5rem 4rem`
- Vertical rhythm: `gap: 1.5rem` between major sections

**Grid Patterns:**
```css
/* Summary cards (dashboard stats) */
.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

/* TV display (dual column) */
.tv-main {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 420px), 1fr));
  gap: clamp(1rem, 2vw, 2rem);
  max-width: 1600px;
  margin: 0 auto;
}
```

### Spatial Scale

```css
--space-xs: 0.35rem  (5.6px)    /* Tight gaps (nav links, badge padding) */
--space-sm: 0.5rem   (8px)      /* Small gaps (inline elements) */
--space-md: 1rem     (16px)     /* Standard gap (cards, sections) */
--space-lg: 1.5rem   (24px)     /* Large gap (major sections) */
--space-xl: 2rem     (32px)     /* Extra large (page padding) */
```

Apply consistently: form gaps use `1rem`, section margins use `1.5rem`, page padding uses `2rem+`.

### Border Radius

```css
--radius-sm: 0.5rem   (8px)     /* Buttons, inputs, badges */
--radius-md: 0.75rem  (12px)    /* Cards, details panels */
--radius-lg: 1rem     (16px)    /* Large cards */
--radius-xl: 1.25rem  (20px)    /* TV main card */
--radius-pill: 999px            /* Badges, status pills */
```

**Application:**
- Buttons, inputs, small UI: `--radius-sm` (0.5rem)
- Admin cards, details: `--radius-md` (0.75rem)
- TV display cards: `--radius-xl` (20px) for prominence
- Badges: `999px` for pill shape

### Elevation & Shadow

```css
--shadow-sm: 0 2px 8px rgba(43, 42, 38, 0.10);   /* Subtle lift */
--shadow-md: 0 8px 24px rgba(43, 42, 38, 0.12);  /* Elevated cards */
```

**Rules:**
- Use `--shadow-sm` for interactive elements (active nav, focused inputs).
- Use `--shadow-md` sparingly for primary surfaces (TV cards).
- **Do not stack shadows** or create multi-layer elevation systems. Two levels maximum.
- Shadow color uses `--text` base for warm consistency.

### Borders

- Default: `1px solid var(--border)`
- Active nav accent: `border-left: 0.35rem solid var(--text)` (thick left indicator)

## Components & Affordances

### Buttons

**Primary Button:**
```css
min-height: 3.5rem;
padding: 0.8rem 1.4rem;
font-size: 1.1rem;
font-weight: 700;
border-radius: var(--radius-sm);
background: var(--primary);
color: white;
cursor: pointer;
transition: background 0.15s ease;
```

**Small Button (`.btn-sm`):**
```css
padding: 0.5rem 0.85rem;
font-size: 0.9rem;
min-height: auto;
```

**Secondary Button (`.btn-secondary`):**
```css
background: var(--primary-soft);
color: var(--text);
```

**States:**
- Hover: Darken background slightly or shift to `--primary-soft`
- Disabled: `opacity: 0.45`, `cursor: not-allowed`
- Focus: Outline with `--focus` color (avoid glow effects)

### Form Inputs

```css
input, select, textarea {
  padding: 0.65rem 0.85rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 1rem;
  background: var(--surface);
  color: var(--text);
}

input:focus, select:focus {
  outline: 2px solid var(--focus);
  outline-offset: 2px;
}
```

**Patterns:**
- Labels above inputs: `display: grid; gap: 0.35rem;`
- Inline forms: `display: flex; align-items: end; gap: 1rem;`
- Placeholder text: Use muted, instructive examples ("Contoh: Muhammad Andi")

### Badges

```css
.badge {
  display: inline-flex;
  align-items: center;
  padding: 0.3rem 0.75rem;
  border-radius: 999px;
  font-size: 0.8rem;
  font-weight: 600;
}

.badge.success { background: #c6f6d5; color: #22543d; }
.badge.error { background: #ff6b6b; color: white; }
.badge.warning { background: #fff0b8; color: var(--text); }
.badge.inactive { background: #ffd0a8; color: var(--text); }
```

Use badges for **status indicators only** (active/inactive, connection state, attendance result). Avoid decorative use.

### Cards

**Admin Card:**
```css
background: var(--surface);
border: 1px solid var(--border);
border-radius: var(--radius-md);
padding: 1.25rem;
```

**TV Display Card:**
```css
background: var(--surface);
border: 1px solid var(--border);
border-radius: 20px;
padding: clamp(1.5rem, 3vw, 2.5rem);
box-shadow: var(--shadow-md);
```

### Tables

```css
table {
  width: 100%;
  border-collapse: collapse;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}

th {
  background: var(--bg);
  font-weight: 700;
  text-align: left;
  padding: 0.75rem 1rem;
  border-bottom: 2px solid var(--border);
}

td {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border);
}
```

### Sidebar Navigation

```css
.sidebar-nav a {
  display: flex;
  align-items: center;
  padding: 0.65rem 0.85rem;
  border-radius: var(--radius-sm);
  color: var(--text);
  font-weight: 700;
  text-decoration: none;
  transition: background 0.15s ease;
}

.sidebar-nav a:hover {
  background: var(--surface);
}

.sidebar-nav a[aria-current="page"] {
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 0.35rem solid var(--text);
  box-shadow: var(--shadow-sm);
}
```

**Active state uses left accent bar** (0.35rem thick) instead of color-only differentiation.

### Empty States

```css
.empty-table-notice {
  background: var(--primary-soft);
  border: 1px dashed var(--border);
  border-radius: var(--radius-md);

## Motion & Micro-interactions

### Transitions

```css
/* Button hover/focus */
transition: background 0.15s ease, border-color 0.15s ease;

/* Nav link hover */
transition: background 0.15s ease, color 0.15s ease;

/* Toggle switch */
transition: background 0.2s ease;
```

**Duration scale:**
- **0.15s:** Fast feedback (buttons, links, inputs)
- **0.2s:** Medium feedback (toggle switches, visibility changes)
- **0.3s+:** Reserved for entry/exit animations (currently unused)

**Easing:** Use `ease` for general transitions. Avoid `ease-in-out` or custom cubic-bezier unless specifically needed for natural motion.

### Hover Behaviors

- **Buttons:** Background color shift (primary → darker, secondary → soft)
- **Links:** Background fill (transparent → `--surface` on sidebar nav)
- **Pagination buttons:** Background shift to `--primary-soft`

### Active/Pressed States

- **Buttons:** No scale transform or shadow change on click (keep it simple)
- **Nav links:** Immediate background + left border accent (no transition on active state)
- **Toggle switch:** Instant color flip (success ↔ gray)

### Focus Indicators

```css
:focus-visible {
  outline: 2px solid var(--focus);
  outline-offset: 2px;
}
```

Use native `outline` property with offset for accessibility. Do not remove focus indicators.

### Animations (TV Display Only)

**Floating animation for idle icon:**
```css
@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-8px); }
}

.tv-idle-icon {
  animation: float 3s ease-in-out infinite;
}
```

## Anti-Patterns / Do Not Use

### Prohibited Visual Patterns

1. **Excessive Gradients**
   - ❌ Do not add gradient borders, gradient text, or multi-stop gradients.
   - ✅ Exception: The subtle `linear-gradient(135deg, #ffffff 0%, #f7fafc 100%)` on dashboard scanner card is acceptable (barely perceptible).

2. **Floating Shadows**
   - ❌ No shadows beyond `--shadow-sm` and `--shadow-md`.
   - ❌ No `0 20px 40px rgba(...)` or multi-layered elevation stacks.
   - ❌ No shadow on hover state changes (buttons remain flat).

3. **Generic Tech Palette**
   - ❌ No indigo (#5a67d8), purple (#9f7aea), or neon blues outside established palette.
   - ❌ Do not replace `--aquamarine` with generic teal or mint variations.
   - ✅ The aqua/sky/mint palette is distinctive to this project—preserve it.

4. **Over-Animated UI**
   - ❌ No scale transforms on button clicks.
   - ❌ No slide-in/fade-in animations for static content.
   - ❌ No parallax, rotation, or bounce effects.
   - ✅ Exception: `float` animation on TV idle icon only.

5. **Decorative Elements**
   - ❌ No icon libraries (currently using emoji for quick visual cues—acceptable).
   - ❌ No background patterns, textures, or decorative SVGs.
   - ❌ No glassmorphism (blurred backgrounds, transparency overlays).

6. **Inconsistent Spacing**
   - ❌ Avoid arbitrary padding values (e.g., `padding: 0.73rem`).
   - ✅ Stick to the spatial scale: 0.35rem, 0.5rem, 1rem, 1.5rem, 2rem.

7. **Non-Semantic Color Use**
   - ❌ Do not use `--success` for non-success states (e.g., generic highlights).
   - ❌ Do not mix arbitrary hex colors outside the defined palette.
   - ✅ All colors must map to CSS variables from `theme.css`.

8. **Excessive Typography Variation**
   - ❌ No additional font weights beyond 400, 600, 700, 800.
   - ❌ No letter-spacing adjustments except TV display headings (`letter-spacing: 0.05em` for uppercase labels).
   - ❌ No italic unless marking user-generated placeholder text or metadata.

9. **Complex Layouts**
   - ❌ No CSS Grid beyond `repeat(auto-fit, minmax(...))` pattern.
   - ❌ No nested grids or flex-within-grid complexity without clear purpose.
   - ✅ Prefer simple flex for inline forms, grid for card galleries.

10. **Custom Form Styling**
    - ❌ Do not fully restyle checkboxes/radio buttons unless accessibility is maintained.
    - ❌ No custom select dropdowns with JS (use native `<select>`).
    - ✅ Exception: Toggle switch for scanner control (functional necessity).

---


**Purpose:** Gentle motion to indicate scanner readiness on TV display. **Do not apply to admin interface.**

---

  padding: 1.25rem 1.5rem;
  text-align: center;
  color: var(--text-muted);
  font-style: italic;
}
```

## Implementation Notes

### Base CSS Files

1. **`pico.min.css`** — Minimal CSS framework (bundled, do not override aggressively)
2. **`theme.css`** — Color tokens, layout, component styles (primary customization file)
3. **`app.css`** — Page-specific overrides (scanner page, admin header)

### CSS Variable Usage

Always reference tokens via `var()`:
```css
/* ✅ Correct */
background: var(--surface);
color: var(--text);

/* ❌ Wrong */
background: #ffffff;
color: #2b2a26;
```

### Responsive Breakpoints

No explicit media queries defined. Layout uses:
- **Flexible grids:** `auto-fit` and `minmax()` for natural reflow
- **Clamp typography:** `clamp(min, preferred, max)` for TV display
- **Viewport units:** `vw` for TV responsive sizing

If adding breakpoints, follow mobile-first approach:
```css
/* Base (mobile) */
.element { ... }

/* Tablet+ */
@media (min-width: 768px) { ... }

/* Desktop+ */
@media (min-width: 1024px) { ... }
```

### Dark Mode

**Not implemented.** The system assumes daylit environments (school/daycare setting). Do not add dark mode without user research and testing for legibility on TV displays.

### Print Styles

**Not implemented.** Reports are exported as `.xlsx` files. If adding print styles, prioritize table legibility and remove sidebar/navigation.

---

## Design Rationale

### Why Aquamarine/Sky Blue?

The palette evokes **calm, cleanliness, and trust**—appropriate for a childcare/educational setting. Aquamarine (`#a5ffd6`) is uncommon in SaaS design, giving the system a distinctive identity. The warm text color (`#2b2a26`) grounds the cool palette and improves readability.

### Why System Fonts?

The app runs on Windows PCs with Edge browser in kiosk mode. Segoe UI is optimized for ClearType rendering and loads instantly. Custom fonts add latency and potential rendering inconsistencies on TV displays.

### Why Minimal Shadows?

TV displays viewed at distance don't benefit from subtle shadows. The design prioritizes **border contrast** over elevation. Shadows are used only where functional (active nav state, card separation).

### Why No Icon Library?

The app uses emoji for quick visual cues (🎴 for card tap, 🟢 for live status, ⚠️ for penalties). Emoji render natively across systems without external dependencies. If scaling, consider a minimal SVG icon set (Lucide, Heroicons) but avoid Font Awesome's bloat.

---

## Maintenance Guidelines

1. **Before adding a new color:** Check if an existing token can serve the purpose. Resist palette expansion.
2. **Before adding a new component:** Audit existing patterns in `theme.css` for reusable styles.
3. **Before adding animation:** Question if it improves usability or is decorative. Default to static unless TV display context.
4. **Before adding a CSS library:** Evaluate if 10-20 lines of custom CSS can achieve the same result. Minimize dependencies.

---

## References

- **Source files:** `app/static/css/theme.css`, `app/static/css/app.css`
- **Template patterns:** `app/templates/admin/base.html`, `app/templates/scan.html`
- **Color palette origin:** Custom-designed for TPA Ulul Albab branding (not AI-generated slop)
- **Accessibility:** Targets WCAG AA for color contrast; full validation requires manual testing

---

**Last updated:** 2026-11-03  
**Design version:** 1.0 (matches current codebase state)

