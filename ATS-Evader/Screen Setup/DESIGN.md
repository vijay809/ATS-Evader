---
name: Synthetic Intelligence Interface
colors:
  surface: '#131313'
  surface-dim: '#131313'
  surface-bright: '#393939'
  surface-container-lowest: '#0e0e0e'
  surface-container-low: '#1c1b1b'
  surface-container: '#201f1f'
  surface-container-high: '#2a2a2a'
  surface-container-highest: '#353534'
  on-surface: '#e5e2e1'
  on-surface-variant: '#c1c6d7'
  inverse-surface: '#e5e2e1'
  inverse-on-surface: '#313030'
  outline: '#8b90a0'
  outline-variant: '#414755'
  surface-tint: '#adc6ff'
  primary: '#adc6ff'
  on-primary: '#002e69'
  primary-container: '#4b8eff'
  on-primary-container: '#00285c'
  inverse-primary: '#005bc1'
  secondary: '#ecb2ff'
  on-secondary: '#520071'
  secondary-container: '#cf5cff'
  on-secondary-container: '#480063'
  tertiary: '#ffb595'
  on-tertiary: '#571e00'
  tertiary-container: '#ef6719'
  on-tertiary-container: '#4c1a00'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#d8e2ff'
  primary-fixed-dim: '#adc6ff'
  on-primary-fixed: '#001a41'
  on-primary-fixed-variant: '#004493'
  secondary-fixed: '#f8d8ff'
  secondary-fixed-dim: '#ecb2ff'
  on-secondary-fixed: '#320047'
  on-secondary-fixed-variant: '#74009f'
  tertiary-fixed: '#ffdbcc'
  tertiary-fixed-dim: '#ffb595'
  on-tertiary-fixed: '#351000'
  on-tertiary-fixed-variant: '#7c2e00'
  background: '#131313'
  on-background: '#e5e2e1'
  surface-variant: '#353534'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  label-caps:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.1em
  data-mono:
    fontFamily: JetBrains Mono
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  unit: 8px
  container-padding: 24px
  gutter: 16px
  stack-sm: 4px
  stack-md: 12px
  stack-lg: 24px
---

## Brand & Style

The design system is engineered for an AI Recruitment Assistant, projecting a persona of hyper-efficiency, precision, and futuristic intelligence. The target audience includes high-growth tech recruiters and talent acquisition leads who require a "command center" experience that feels both powerful and effortless.

The visual style is **Glassmorphism**, characterized by translucent layers, heavy backdrop blurs, and thin, high-precision borders. This creates a sense of depth and modularity, suggesting that the AI operates on a multi-dimensional plane of data. The emotional response is one of calm authority and "high-end" technical sophistication. Surfaces are not solid; they are crystalline filters over a deep, atmospheric void.

## Colors

The palette is anchored in a **Deep Charcoal** foundation to minimize eye strain during long recruitment sessions and to maximize the "pop" of generative AI elements. 

- **Primary (Electric Blue):** Used for critical actions, active states, and AI-driven insights.
- **Secondary (Cyber Purple):** Reserved for "Magic" moments—automated scheduling, candidate matching, and predictive analytics.
- **Surface Strategy:** Backgrounds use `#121212`. Elevated containers use `#181818` with a 60% opacity and a `20px` backdrop blur.
- **Borders:** All glass elements are defined by a `1px` translucent white stroke (`rgba(255, 255, 255, 0.08)`) to catch light, simulating a physical glass edge.

## Typography

This design system utilizes **Inter** for its clean, systematic legibility across complex data sets. To reinforce the technical nature of the AI, **JetBrains Mono** is introduced for labels, metadata, and candidate IDs.

- **High Contrast:** Headlines use a bold weight with negative letter spacing to feel "locked in" and authoritative.
- **Readability:** Body text maintains a generous line height to ensure candidate profiles and AI summaries are easily scannable.
- **Technical Accents:** All-caps monospaced labels are used for status badges and secondary navigation to provide a "developer-lite" aesthetic.

## Layout & Spacing

The layout follows a **Fixed Grid** philosophy for the desktop "Command Center" view, ensuring that AI widgets remain in predictable positions for muscle memory. 

- **Desktop:** 12-column grid with a fixed sidebar (280px) and a fluid content area.
- **Rhythm:** An 8px linear scale governs all padding and margins. 
- **Density:** The UI is "Compact-Professional." Use `12px` (stack-md) for internal element spacing within cards to maximize information density without clutter.
- **Glass Margins:** Floating glass panels should maintain a minimum `16px` gutter between each other to allow the background atmosphere to breathe through.

## Elevation & Depth

Depth is communicated through **Z-axis Layering** rather than traditional shadows. 

1. **Base Layer:** `#121212` solid background.
2. **Intermediate Layer:** Glass panels with `20px` backdrop-blur and `1px` border.
3. **Active/Modal Layer:** Higher opacity glass (`rgba(30, 30, 30, 0.8)`) with a subtle "Outer Glow" in the Primary color (`#007AFF`) at low opacity (10-15%) to simulate light emission from the screen.

Shadows, where used, should be ultra-diffused: `0px 10px 40px rgba(0, 0, 0, 0.5)`.

## Shapes

The shape language balances modern softness with technical precision.

- **Standard Containers:** `0.5rem (8px)` corner radius provides a clean, professional look.
- **Interactive Elements:** Buttons and Input fields also follow the `8px` rule to maintain a consistent silhouette.
- **Glass Panels:** Large dashboard sections use `1rem (16px)` to soften the overall "Command Center" feel and make the glass look like high-quality molded acrylic.

## Components

### Buttons
- **Primary:** Gradient fill (Electric Blue to Cyber Purple), white text, and a `15px` outer glow on hover.
- **Ghost/Glass:** Transparent background, `1px` white border (20% opacity), backdrop-blur.

### Glass Cards
- Used for candidate profiles and AI insights. Must feature a `linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(255,255,255,0.05) 100%)` overlay to simulate a light sheen.

### Input Fields
- Dark, recessed fill (`#080808`) with a subtle inner shadow. On focus, the border transitions to Electric Blue with a faint outer glow.

### Status Badges
- Small, pill-shaped markers using `JetBrains Mono`. Use a "Glowing Dot" indicator (e.g., a 6px circle with a `4px` blur) next to the text to indicate "AI Processing" or "Active" states.

### Navigation
- A compact vertical rail on the left. Icons use thin strokes (1.5px). Active states are indicated by a vertical "Light Bar" (2px wide) on the edge of the screen in Cyber Purple.