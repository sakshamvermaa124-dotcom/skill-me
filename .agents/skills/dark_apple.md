# Dark Apple Design

## Purpose

Use this skill when designing or redesigning a web application, dashboard, SaaS product, or interface with a **premium Apple-inspired dark theme**.

The goal is not to copy Apple literally. The goal is to achieve the qualities Apple design is known for:

* Extreme visual clarity
* Calm and intentional hierarchy
* Premium materials
* Generous whitespace
* Subtle depth
* Excellent typography
* Minimal visual noise
* Smooth interactions
* High information density without feeling crowded

The final result should feel like a polished product made by an elite product design team, not a generic “dark mode dashboard with glowing cards”.

---

# Core Design Philosophy

## 1. Darkness should feel like material, not emptiness

Avoid pure black backgrounds everywhere.

Use layered dark surfaces:

```text
Page background:        #08090B
Secondary background:   #0D0F12
Elevated surface:       #14161A
Interactive surface:    #1A1D22
Active surface:         #202329
```

The interface should feel like physical layers floating subtly above one another.

Do not create separation primarily using borders.

Prefer this hierarchy:

```text
Background
  ↓
Surface contrast
  ↓
Soft shadow
  ↓
Subtle border
```

Borders should usually be extremely low contrast.

---

# 2. Matte over glossy

The default aesthetic is **matte, soft, and tactile**.

Avoid:

* Excessive glassmorphism
* Neon glows
* Strong gradients
* Chrome effects
* Highly reflective surfaces
* Heavy blur
* Cyberpunk styling
* Obvious futuristic decorations

Prefer:

* Soft diffuse shadows
* Very subtle gradients
* Slight surface elevation
* Low-opacity borders
* Controlled highlights

The UI should feel closer to:

> Precision-machined dark hardware

than:

> A glowing spaceship dashboard

---

# 3. Use one dominant accent system

Do not assign random colors to every card.

The default accent should be restrained.

Recommended palette:

```text
Primary accent:     #0A84FF
Success:            #30D158
Warning:            #FFD60A
Danger:             #FF453A
Purple:             #BF5AF2
Orange:             #FF9F0A
```

Use accent colors primarily for:

* Important actions
* Active states
* Status indicators
* Progress
* Small icon accents

Do not color entire sections unless the status is important.

For example:

Good:

```text
Dark card
Small green icon
Green status text
Neutral content
```

Avoid:

```text
Entire green card
Green background
Green border
Green glow
Green text
```

Humans already struggle with visual restraint. Do not help them fail harder.

---

# Layout Rules

## 4. Prioritize whitespace

Every major section should have room to breathe.

Use:

```text
Page padding:          32–48px
Large section gaps:    24–32px
Card padding:          20–28px
Small component gaps:  8–16px
```

Never reduce spacing just to fit more content.

If the interface feels crowded:

1. Remove unnecessary elements.
2. Group related information.
3. Increase hierarchy.
4. Only then consider reducing spacing.

Do not solve poor information architecture with tiny margins.

---

# 5. Use strong visual grouping

Each section should answer one question.

For example:

```text
Dashboard
│
├── Primary action/status
│
├── Key metrics
│
├── Progress
│
├── Supporting information
│
└── Timeline or activity
```

Do not create separate cards for every small piece of information.

Use cards only when they create meaningful grouping.

---

# Cards

## 6. Cards should feel like quiet surfaces

Default card styling:

```css
background: rgba(20, 22, 26, 0.85);
border: 1px solid rgba(255, 255, 255, 0.07);
border-radius: 20px;
box-shadow:
  0 1px 2px rgba(0, 0, 0, 0.35),
  0 12px 40px rgba(0, 0, 0, 0.18);
```

Use stronger elevation only for:

* Modals
* Important actions
* Floating controls
* Selected states

Avoid making every card look equally important.

---

## 7. Selected states should be subtle

Do not use thick glowing borders.

Preferred selected state:

```css
background: rgba(255, 255, 255, 0.04);
border-color: rgba(10, 132, 255, 0.65);
box-shadow:
  0 0 0 1px rgba(10, 132, 255, 0.12);
```

The selected state should be noticeable without screaming.

---

# Typography

## 8. Typography is the primary hierarchy system

Prefer:

```text
SF Pro
Inter
Geist
Manrope
```

Use no more than two font families.

Recommended hierarchy:

```text
Hero:        32–40px / Semibold
Section:     22–28px / Semibold
Card title:  15–18px / Medium
Body:        14–16px / Regular
Metadata:    12–13px / Medium
```

Use opacity and size differences instead of excessive font weights.

Typical dark theme text:

```text
Primary:     rgba(255,255,255,0.92)
Secondary:   rgba(255,255,255,0.65)
Tertiary:    rgba(255,255,255,0.42)
```

Avoid pure white for every text element.

---

# Buttons

## 9. Buttons should feel precise

Use rounded rectangles with controlled corner radii.

Recommended:

```text
Primary button:      12–16px radius
Secondary button:    12–16px radius
Icon button:         12–14px radius
Pills:               only for filters or compact statuses
```

Do not make every button a pill.

Primary action:

```text
Solid accent background
Clear white label
Minimal shadow
```

Secondary action:

```text
Dark surface
Subtle border
Neutral label
```

Hover effects should be minimal:

```text
Slight brightness increase
Tiny elevation
Fast transition
```

Never animate buttons like arcade machines.

---

# Icons

## 10. Icons should support, not decorate

Use a single icon family throughout the interface.

Recommended style:

```text
Lucide
SF Symbols-inspired icons
Thin-to-medium stroke icons
```

Rules:

* Use consistent stroke widths.
* Keep icon containers minimal.
* Avoid putting every icon inside a colored square.
* Use accent colors only when status or hierarchy requires them.

Preferred:

```text
Small icon + text
```

Instead of:

```text
Large glowing icon
Colored container
Gradient background
Shadow
```

---

# Sidebar

## 11. Navigation should feel integrated

The sidebar should be visually quiet.

Inactive items:

```text
Muted icon
Transparent background
```

Active item:

```text
Subtle elevated surface
Small accent indicator
Slightly brighter icon
```

Do not highlight the active item with an enormous colored rectangle.

The navigation should guide the user without competing with the content.

---

# Progress and Data

## 12. Data visualization should remain simple

Prefer:

* Linear progress bars
* Circular completion indicators
* Small status dots
* Minimal sparklines
* Clear numeric hierarchy

Avoid unnecessary charts.

For progress:

```text
Track:    low-contrast neutral
Progress: one accent color
Marker:   optional, only if meaningful
```

Do not add gradients unless they communicate progress or status.

---

# Status System

## 13. Status should be understandable instantly

Use color plus another signal.

Examples:

```text
Completed
✓ Green indicator
Completed label

Active
Blue indicator
Active label

Pending
Muted indicator
Pending label

Locked
Muted icon
Locked state
```

Never rely only on color.

---

# Motion

## 14. Motion should feel natural

Use short, smooth transitions.

Recommended:

```css
transition: 180ms ease-out;
```

For larger surfaces:

```css
transition: 250ms cubic-bezier(0.2, 0, 0, 1);
```

Preferred motion:

* Fade
* Small translate
* Small scale
* Gentle elevation

Avoid:

* Bouncing
* Spinning
* Excessive glowing
* Dramatic entrance animations
* Constant motion

The user should notice the result, not the animation.

---

# Responsive Design

## 15. Preserve hierarchy on smaller screens

Do not simply shrink the desktop layout.

For mobile:

```text
Multi-column → single column
Sidebar → compact navigation
Secondary actions → overflow menu
Large metric grids → horizontal scroll or stacked cards
Timeline → vertical or scrollable
```

Maintain:

* Clear primary action
* Readable typography
* Comfortable touch targets
* Logical grouping

Minimum touch target:

```text
44 × 44px
```

---

# Design Review Checklist

Before finalizing, inspect the UI and ask:

### Hierarchy

* Is the most important information obvious within 3 seconds?
* Are there too many competing visual elements?
* Does every card have a purpose?

### Spacing

* Does the layout feel calm?
* Are related elements closer together than unrelated elements?
* Is there enough negative space?

### Dark Theme

* Are surfaces layered rather than uniformly black?
* Are borders subtle?
* Is contrast sufficient?

### Color

* Is there a dominant accent?
* Are colors used semantically?
* Are there unnecessary gradients or glows?

### Typography

* Is the hierarchy clear without excessive font sizes?
* Are secondary labels sufficiently muted?
* Is text readable at a glance?

### Interaction

* Are hover and active states subtle?
* Are buttons clearly distinguishable?
* Are touch targets accessible?

---

# Mandatory Avoid List

Do NOT automatically use:

* Glassmorphism everywhere
* Neon gradients
* Purple-blue cyberpunk palettes
* Thick glowing borders
* Random accent colors
* Excessive rounded pills
* Floating particles
* Decorative grids
* Oversized icons
* Heavy blur
* Every element inside a card
* Excessive badges
* Tiny low-contrast text
* “Futuristic” visual noise

If a design element does not improve:

```text
Hierarchy
Usability
Feedback
Meaning
```

remove it.

---

# Final Standard

The finished design should feel:

```text
Premium
Quiet
Confident
Intentional
Matte
Highly usable
Modern
Emotionally restrained
```

A good test:

> If all accent colors were removed, would the interface still have excellent hierarchy and usability?

If the answer is no, the design is relying on decoration instead of design.

The target is a dark interface that feels expensive because of **proportion, spacing, typography, material depth, and restraint**, not because somebody discovered the CSS `box-shadow` property and became intoxicated by it.
