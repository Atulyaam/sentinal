# Steering Directive — UI Design, Aesthetics & Accessibility
**Project Sentinel — Kiroween 2026**

## 1. Visual Identity & Aesthetic Principles
Sentinel is an evidence-first, high-precision security investigation workbench. Its visual language prioritizes clarity, calm focus, and defensibility over flashiness or novelty.

- **Color Palette:**
  - Background: Deep graphite and near-black surfaces (`#0B0D11`, `#11141B`, `#161B22`).
  - Borders: Crisp, hairline borders (`#21262D`, `#30363D`) providing structural definition.
  - Text: High contrast primary text (`#F0F6FC`), muted secondary text (`#8B949E`), subtle tertiary metadata (`#6E7681`).
  - Brand Accent: Controlled cobalt / indigo (`#388BFD`, `#1F6FEB`) reserved for active navigation, focus rings, and primary actions.
  - Semantic Status Colors:
    - High / Critical: Ruby red (`#F85149`, background `#3E1818`)
    - Medium / Warning: Amber (`#D29922`, background `#382A0F`)
    - Low / Info: Blue / Cyan (`#58A6FF`, background `#0C2D6B`)
    - Clean / Verified: Emerald green (`#3FB950`, background `#0E3A1E`)
    - Blocked / Rejected: Crimson / Coral (`#FF7B72`, background `#4A1515`)
- **Prohibited Decorative Elements:**
  - **No Emoji Interface Icons:** Never use emojis (e.g. 🚨, ⚠️, 🔒, 📊) for buttons, route navigation, or status badges. Use purpose-built SVG line icons (e.g., Lucide).
  - **No Sci-Fi / Cyberpunk Gimmicks:** No matrix rain, glowing text shadows, CRT scanlines, or decorative neon gradients.
  - **No Fake Metrics:** Never render decorative charts showing made-up threat percentages or fictional risk scores.

## 2. Typography & Spatial Rhythm
- **Font Stack:** Clean, legible sans-serif (`Inter`, system sans-serif) for interface copy; tabular monospace (`JetBrains Mono`, `Consolas`, monospace) for timestamps, hashes, IPs, and event records.
- **Spacing System:** Base 4px/8px grid system (`gap-2`, `gap-4`, `p-4`, `p-6`). Dense and informative without feeling cramped.

## 3. Mandatory UI State Matrix
Every view in the application must account for five distinct lifecycle states:
1. **Loading State:** Subtle skeleton or indicator communicating active fetching.
2. **Empty State:** Clear, constructive explanation of why no records exist and instructions on how to populate data.
3. **Error State:** Human-readable diagnosis of what failed, with actionable recovery steps.
4. **Backend Unavailable State:** Non-destructive warning showing that the investigation engine is offline, with reconnect status.
5. **Normal Connected State:** Active, interactive interface presenting verified data.

## 4. Accessibility Expectations (WCAG 2.1 AA)
- Semantic HTML elements (`<nav>`, `<main>`, `<header>`, `<article>`, `<button>`).
- High-contrast visual focus rings (`outline: 2px solid #388BFD`) visible on keyboard tab navigation.
- Accessible ARIA labels on all interactive controls.
- Color is never the sole conveyor of information (always accompanied by text or icon).
- Support for `prefers-reduced-motion` media queries.

