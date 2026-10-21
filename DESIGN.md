---
name: MarketplaceX
description: A boutique carrier bag and hang tag; calm paper, one deep bottle green, prices on die-cut tags.
colors:
  paper: "#f6f7f5"
  surface: "#ffffff"
  ink: "#16201b"
  muted: "#56645c"
  line: "#dde3df"
  line-strong: "#c4ccc7"
  bag: "#1f4d3a"
  bag-deep: "#143326"
  bag-tint: "#e8efeb"
  brass: "#d4b062"
  danger: "#b3261e"
  danger-tint: "#fbeceb"
  ok: "#2a7149"
  ok-tint: "#e6f2ea"
  warn: "#8a5a00"
  warn-tint: "#fbf1dc"
  ink-0: "#b5600f"
  ink-1: "#a2402c"
  ink-2: "#2c5a85"
  ink-3: "#7f611a"
  ink-4: "#683c78"
  ink-5: "#2a6f62"
  ink-6: "#9b3a5d"
  ink-7: "#3b4a5e"
typography:
  page-title:
    fontFamily: "Be Vietnam Pro, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "clamp(1.6rem, 1.2rem + 1.2vw, 2.2rem)"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  section:
    fontFamily: "Be Vietnam Pro, system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
    letterSpacing: "-0.02em"
  body:
    fontFamily: "Be Vietnam Pro, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.55
  plate-title:
    fontFamily: "Be Vietnam Pro, system-ui, sans-serif"
    fontSize: "0.9rem"
    lineHeight: 1.4
  label:
    fontFamily: "Be Vietnam Pro, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    letterSpacing: "0.06em"
  wordmark:
    fontFamily: "Be Vietnam Pro, system-ui, sans-serif"
    fontSize: "1.05rem"
    fontWeight: 700
    letterSpacing: "0.32em"
rounded:
  sm: "7px"
  md: "10px"
  lg: "14px"
  pill: "999px"
spacing:
  xs: "0.25rem"
  sm: "0.5rem"
  md: "1rem"
  lg: "1.5rem"
  xl: "3rem"
components:
  button-primary:
    backgroundColor: "{colors.bag}"
    textColor: "{colors.surface}"
    rounded: "{rounded.md}"
    padding: "0.5rem 1.05rem"
  button-primary-hover:
    backgroundColor: "{colors.bag-deep}"
  button-outline:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "0.5rem 1.05rem"
  shell:
    backgroundColor: "{colors.bag}"
    textColor: "{colors.surface}"
    height: "64px"
  hang-tag:
    backgroundColor: "{colors.bag}"
    textColor: "{colors.surface}"
    padding: "0.42rem 0.7rem 0.42rem 1.35rem"
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.md}"
    padding: "1.5rem"
  punched-tracker:
    backgroundColor: "{colors.bag}"
    textColor: "{colors.bag-tint}"
    rounded: "{rounded.lg}"
    padding: "1.4rem 1.25rem 1.1rem 3rem"
---

# Design System: MarketplaceX

## Overview

**Creative North Star: "The Boutique Carrier Bag"**

A calm shop, not a bazaar. Cool white paper holds the page, one deep bottle green (the bag) carries the shell and every primary action, and product photos sit on identical white square plates so the goods lead. Brass appears only on the wordmark, the live-step glow, the cart count and focus. Rules are hairlines, corners are 10px, and there are no gradients or glass.

The signature is the hang tag: prices are die-cut tags with a punched hole, and order tracking is a row of four holes punched in sequence. The voice is clean, editorial and premium, so it passes for a real store while every table row stays easy to read.

**Key Characteristics:**
- Bottle-green shell on cool paper; ink near-black text.
- Be Vietnam Pro everywhere (full Vietnamese diacritics); wordmark in tracked caps.
- Hairline borders, flat surfaces, shadow only on hover and floating layers.
- Each of the 8 categories owns one fixed tag ink.
- Bootstrap 5 underneath, re-skinned through its custom properties.

## Colors

Restrained: paper, white and ink, one green, one brass.

### Primary
- **Bottle Green Bag** (#1f4d3a): shell, primary buttons, active ops-nav, selection, links. **Deep Bag** (#143326) is hover and pressed. **Bag Tint** (#e8efeb) is hover wash and selected payment option.

### Secondary
- **Brass Foil** (#d4b062): wordmark, focus ring, cart count, the current tracker step. Nothing else.

### Neutral
- **Cool Paper** (#f6f7f5) page ground; **Surface White** (#ffffff) plates, panels, tables; **Ink** (#16201b) text; **Muted Moss** (#56645c) secondary text; **Hairline** (#dde3df) and **Strong Hairline** (#c4ccc7) borders.

### Status and category
- Semantic: danger #b3261e, ok #2a7149, warn #8a5a00, each with a pale tint for alerts and stamps.
- Category inks ink-0..ink-7 colour a category's dot, heading marker, chip and price tag. Assigned as category_id mod 8.

### Named Rules
**The Brass Is Rare Rule.** Brass marks the wordmark, focus and the live step only; never a button fill or a decoration.
**The Fixed Ink Rule.** A category keeps one ink everywhere it appears.

## Typography

**Font:** Be Vietnam Pro (fallback system-ui, Segoe UI, sans-serif) for all text.

**Character:** One family, weight and size do the work. Headings are 600 with -0.02em tracking and balanced wrapping.

### Hierarchy
- **Page title** (600, clamp 1.6-2.2rem): one per page.
- **Section head** (600, 1.25rem): category and panel groups, with a coloured dot.
- **Body** (400, 15px, 1.55): descriptions capped at 65ch.
- **Plate title** (0.9rem, 1.4, two-line clamp): product names.
- **Label** (600, 0.75rem, 0.06em, uppercase): table column heads only.
- **Wordmark** (700, tracked 0.32em, caps).

### Named Rules
**The Tabular Money Rule.** Prices, counts and times use tabular numerals.

## Layout

Bootstrap container grid; product lists are 4-up plates collapsing responsively. Page rhythm: 3rem between sections, 1rem inside section heads, 1.5rem panel padding. The shell is sticky at 64px minimum; at 576px the search field wraps to its own full-width row and link labels hide. Login splits into two columns until 860px. The product buy box is sticky at top 96px on desktop and static below 860px. Admin stats are a 4-up hairline grid, 2-up on mobile.

## Elevation & Depth

Flat by default; hairlines separate. Shadow is a response or a float: plates gain the soft green-tinted shadow on hover (`0 1px 2px rgba(20,51,38,.06), 0 8px 24px -12px rgba(20,51,38,.18)`), the login card carries it, and the assistant widget floats on a deeper one.

### Named Rules
**The Flat Until Touched Rule.** Resting surfaces carry no shadow.

## Shapes

Gentle 10px corners for panels, plates and inputs (7px small, 14px large and gallery), pill (999px) for search, chips and status stamps. The hang tag is clipped to a pointed left edge with a punched hole; the tracker is a larger tag in the same die-cut form.

## Components

### Buttons
- Primary: Bottle Green fill, white text, 10px corners, 0.5rem x 1.05rem; hover to Deep Bag over 0.2s. Outline: white fill, strong hairline, bag-tint hover. Danger outline for destructive. Focus is a 2px brass outline, 2px offset.

### Product plate
- Square white plate, hairline border, image contained at 12% padding with multiply blend; below: two-line title, muted brand, then the price hang tag and a muted rating.

### Hang tag (price)
- Category-ink fill, white 600 text, pointed-left clip with a paper-coloured punch hole; large variant (1.6rem) on the product page; muted grey variant for unavailable.

### Status stamps
- Pill with dot, tinted by state (placed grey, processing warn, shipped blue, delivered ok, cancelled danger); payment stamps are outlined without dot.

### Punched tracker (signature)
- Green tag with four holes; done holes are solid white and inset, upcoming are dashed, the current one has a brass ring; the hole animates once on punch (0.6s). Cancelled turns the tag deep red. A compact 10px dot version (punch-sm) appears in order tables.

### Navigation
- Green shell with brass wordmark, white pill search with mic and go buttons, link buttons in pale green-white. Sub-nav is a row of pill chips with category-ink dots; the ops variant drops dots and fills the active chip green.

### Inputs
- Strong hairline, white; focus turns border green with a 3px green 15% halo.

## Do's and Don'ts

### Do:
- **Do** use bag green for every primary action and brass only for wordmark, focus and the live step.
- **Do** put every price on a hang tag in its category ink.
- **Do** keep product photos on identical square white plates.
- **Do** use hairline borders and 10px corners; reserve shadow for hover and floating layers.
- **Do** use tabular numerals for money, counts and times.

### Don't:
- **Don't** use gradients, glass, or an orange marketplace header.
- **Don't** add colour beyond the bag, brass, semantic and eight category inks.
- **Don't** change a category's ink between surfaces.
- **Don't** use motion beyond short state transitions and the single punch; it respects reduced motion.
