---
name: Pastel Modern Job Hunter
colors:
  surface: '#f9f9ff'
  surface-dim: '#d2daed'
  surface-bright: '#f9f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f0f3ff'
  surface-container: '#e7eeff'
  surface-container-high: '#e0e8fb'
  surface-container-highest: '#dbe3f5'
  on-surface: '#141c29'
  on-surface-variant: '#484550'
  inverse-surface: '#29313f'
  inverse-on-surface: '#ecf1ff'
  outline: '#797581'
  outline-variant: '#c9c4d1'
  surface-tint: '#61549b'
  primary: '#5e5298'
  on-primary: '#ffffff'
  primary-container: '#776ab3'
  on-primary-container: '#fffbff'
  inverse-primary: '#cabeff'
  secondary: '#186a59'
  on-secondary: '#ffffff'
  secondary-container: '#a3eed8'
  on-secondary-container: '#1f6e5d'
  tertiary: '#8e4555'
  on-tertiary: '#ffffff'
  tertiary-container: '#ac5d6d'
  on-tertiary-container: '#fffbff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#e6deff'
  primary-fixed-dim: '#cabeff'
  on-primary-fixed: '#1c0b54'
  on-primary-fixed-variant: '#493c81'
  secondary-fixed: '#a6f1db'
  secondary-fixed-dim: '#8ad5c0'
  on-secondary-fixed: '#002019'
  on-secondary-fixed-variant: '#005142'
  tertiary-fixed: '#ffd9de'
  tertiary-fixed-dim: '#ffb2bf'
  on-tertiary-fixed: '#3d0416'
  on-tertiary-fixed-variant: '#743040'
  background: '#f9f9ff'
  on-background: '#141c29'
  surface-variant: '#dbe3f5'
typography:
  display-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 48px
    letterSpacing: -0.02em
  display-lg-mobile:
    fontFamily: Plus Jakarta Sans
    fontSize: 30px
    fontWeight: '700'
    lineHeight: 38px
    letterSpacing: -0.015em
  headline-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 22px
    fontWeight: '600'
    lineHeight: 30px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 26px
  body-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 18px
  label-lg:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
    letterSpacing: 0.02em
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.03em
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 10px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.04em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1.25rem
  gutter-mobile: 0.75rem
  margin: 2rem
  margin-mobile: 1rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2.5rem
---

## Brand & Style

This design system establishes an empathetic, low-stress operational environment for autonomous career agents and job seekers. Job hunting is inherently anxious; the interface counters this tension through a tranquil, tactile aesthetic blending soft modernism with subtle glassmorphic atmospheric depth. 

The aesthetic marries structured modular utility with gentle visual comfort. It pairs airy spatial rhythm and muted pastel cues—soft lilac, calming mint, gentle slate, and warm blush accents—with crisp, high-contrast typographic anchors. Surfaces feel touchable and serene, featuring soft ambient radiance, pill-shaped utility badges, translucent cards, and whisper-soft borders. The overall tone is sophisticated, autonomous, reassuring, and exceptionally focused.

## Colors

The palette relies on gentle, desaturated pastels balanced against crisp text and creamy foundation surfaces to ensure WCAG AA compliance across all workflows.

- **Primary (`#8B7EC8` - Soft Lilac/Wisteria):** Signals automated agent actions, primary CTA controls, active navigational selections, and pipeline focus states.
- **Secondary (`#68B29E` - Muted Mint):** Represents successful matches, verified skill assessments, high compatibility scores (85%+), and automated submissions.
- **Tertiary (`#D98293` - Dusty Rose):** Highlights urgent application deadlines, priority flags, system notices, and delicate caution alerts.
- **Neutral (`#626A7A` - Creamy Slate):** Provides balanced typographic weighting, quiet iconography, and refined structural borders without harsh black contrast.

### Surface and Accent System
- **Canvas Base:** `#F9F9FC` (warm milk tint) with secondary container fills at `#F1F2F8`.
- **Sky Blue Utility (`#7DA8D6`):** Highlights real-time scraping logs, outbound networking triggers, and communication threads.
- **Soft Peach Accent (`#EAA789`):** Indicates pending user reviews, human-in-the-loop validation, and interview preparations.
- **Subtle Glass Borders:** `rgba(139, 126, 200, 0.14)` for lilac elements, and `rgba(98, 106, 122, 0.10)` across standard containers.

## Typography

The type hierarchy pairs **Plus Jakarta Sans** for headlines and running copy with **JetBrains Mono** for console operations, metrics, status codes, and pill badges.

- **Plus Jakarta Sans** injects human warmth, organic roundness, and effortless editorial legibility into dense job descriptions, company briefs, and conversational AI summaries.
- **JetBrains Mono** provides precision alignment for match percentages, salary ranges, telemetry logs, timestamp trackers, and token usage outputs.
- Large display headings maintain negative tracking to keep headlines tight and architectural, while smaller labels adopt open tracking to maintain instant legibility at microscopic scales.

## Layout & Spacing

The console follows a dynamic 12-column fluid grid on desktop viewports (collapsing to 8 columns on tablets and 4 columns on mobile handsets). Outer workspace canvas boundaries use `margin` (`2rem` desktop, `1rem` mobile), while interior structural sections rely on `gutter` scales to sustain breathing room between queue panels, telemetric sidebars, and job pipeline feeds.

A modular 8pt/4pt rhythmic baseline controls internal container spacing:
- **`space-xs` (4px):** Micro gaps between icons and badge text, paired inline status indicators.
- **`space-sm` (8px):** Tight vertical stacks within candidate cards, tag list spacing.
- **`space-md` (16px):** Standard interior component padding for form fields, list nodes, and utility bars.
- **`space-lg` (24px):** Primary card padding and separation between functional modules.
- **`space-xl` (40px):** Major dashboard sectional blocks and pipeline workflow phase delineations.

## Elevation & Depth

Visual hierarchy is constructed through soft, tinted ambient diffusion and layered translucency rather than stark, muddy drop shadows.

- **Level 0 (Base Canvas):** Solid `#F9F9FC`, the quiet canvas foundation.
- **Level 1 (Subsurface Cards & Inset Panels):** `#FFFFFF` with 85% opacity, `backdrop-filter: blur(12px)`, and a hairline outline of `1px solid rgba(98, 106, 122, 0.08)`. Shadow: `0 4px 20px -2px rgba(139, 126, 200, 0.06)`.
- **Level 2 (Interactive Modules & Hover Targets):** `#FFFFFF` with 95% opacity. Shadow: `0 10px 30px -4px rgba(139, 126, 200, 0.12), 0 2px 6px -1px rgba(104, 178, 158, 0.06)`. Border sharpens to `rgba(139, 126, 200, 0.20)`.
- **Level 3 (Modals, Slide-over Prompts, Overlays):** `#FFFFFF` crisp layer over an atmospheric background veil (`rgba(44, 49, 64, 0.20)` with 8px blur). Shadow: `0 24px 48px -8px rgba(98, 106, 122, 0.16), 0 0 24px 0 rgba(139, 126, 200, 0.10)`.

## Shapes

The interface embraces a balanced rounded geometry (`roundedness: 2`, with 0.5rem base radius) to deliver approachable modernism while preserving structural density for high-volume tabular and card data.

- **Standard Elements (0.5rem / 8px):** Input boxes, interactive dropdown menus, table view containers, and contextual popovers.
- **Compound Cards (`rounded-lg` - 1rem / 16px):** Job listing cards, automated workflow tiles, terminal inspector panes, and filter panels.
- **App Containers & Modals (`rounded-xl` - 1.5rem / 24px):** Primary dashboard canvases, slide-out application previews, and modal sheets.
- **Status Badges & Command Buttons:** Fully round pill execution (`border-radius: 9999px`) to emphasize fluidity and dynamic AI status shifts.

## Components

### Buttons
- **Primary Action (Autonomous Run / Submit):** Solid soft lilac (`#8B7EC8`) background, white text, pill shape, soft glow shadow `0 4px 14px rgba(139, 126, 200, 0.35)`. Subtle `translateY(-1px)` shift on hover.
- **Secondary (Inspect / Dry Run):** Pale lilac tint background (`rgba(139, 126, 200, 0.12)`), `#8B7EC8` text, hairline border `rgba(139, 126, 200, 0.25)`.
- **Ghost/Tertiary (Filter / Reset):** Transparent background, creamy slate text (`#626A7A`), subtle hover highlight (`rgba(98, 106, 122, 0.06)`).

### Pill Badges & Chips
- **Match Score Badge:** Pill shape, background muted mint tint (`rgba(104, 178, 158, 0.15)`), text `#2E6B5A`, font `label-md` (JetBrains Mono).
- **Stage Chips (Applied, Review, Ghosted):** Monospaced pill styling tinted according to lifecycle state (e.g., dusty rose for urgent follow-ups, gentle sky blue for in-flight requests).

### Job & Agent Cards
- Surface composed of Level 1 frosted glass with 16px corner radius.
- Header row housing target company glyph, localized salary badge, and match percentage pill.
- Sub-row hosting dynamic tags (e.g., "Full-Time", "Remote", "Agent Ready") in micro-pills with 4px element spacing.
- Hover transition invokes Level 2 elevation and a delicate 1px perimeter glow in `#8B7EC8`.

### Input Fields & Search Controls
- Surface background: `#FFFFFF` or `rgba(255, 255, 255, 0.70)`.
- Rest border: `1px solid rgba(98, 106, 122, 0.18)`, border radius `0.5rem`.
- Focus state: Border transitions to `#8B7EC8`, reinforced by an ambient focus ring (`0 0 0 3px rgba(139, 126, 200, 0.20)`).

### Checkboxes & Toggle Switches
- Checkbox squares utilize `rounded` (4px) with soft lilac fill upon selection and a crisp white tick mark.
- Toggle switches adopt a full pill silhouette; off-state features creamy slate neutral fill (`#D2D6E0`), while active agent execution slides to muted mint (`#68B29E`) with a soft ambient bloom.

### Agent Console Stream (Specialized Component)
- Embedded container using `label-md` / `label-sm` JetBrains Mono text.
- Surface: Creamy slate tint (`rgba(98, 106, 122, 0.05)`) with subtle inset border.
- Stream lines prefixed with pastel color-coded status bullets: Lilac for system operations, Mint for matching completions, Soft Peach for agent decision-tree checkpoints.