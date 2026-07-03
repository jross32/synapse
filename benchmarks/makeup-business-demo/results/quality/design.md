# Visual design — 90 (with Synapse) vs. 46 (without Synapse)

Scored by an independent judge agent that read the full CSS of both apps. This is the largest gap of any dimension.

## With Synapse — 90/100

Reads as a real boutique-beauty brand, not a template. Genuine two-typeface pairing (Playfair Display serif + Nunito sans via Google Fonts) instead of system fonts. A deliberate 10-token color system (deep pink, mid pink, light pink, pale pink, cream, gold, gold-light, dark, medium, text) with a clear hierarchy, versus a flat palette. Generous, rhythmic whitespace (108px section padding, tuned line-heights). Fluid `clamp()` typography with per-use letter-spacing. Micro-details throughout: gradient hero background, soft radial "orb" decorations, a gradient divider under every heading, a frosted-glass sticky header (`backdrop-filter: blur`), gradient hover underlines on cards, pill-shaped price badges.

**Issues found:** an initials/monogram placeholder instead of a real photo (a deliberate stand-in, not a flaw); decorative Unicode glyphs instead of a real icon set; the 3-column service grid feels dense right before its breakpoint.

## Without Synapse — 46/100

Functional but generic. No web fonts loaded at all — falls back entirely to system font stacks (Segoe UI/Arial, Georgia/Times New Roman), so it renders differently per OS and has no distinctive brand voice. A thinner 5-token palette with no light/pale variants, so the same pink is reused almost everywhere. Flat, uniform section padding with no per-section rhythm. Minimal flourishes: one flat two-stop gradient, plain drop-shadow cards, no sticky header, no mobile menu, no image/placeholder in the About section at all.

**Issues found:** the success-message green (`#eaf7ee`/`#2e7d4f`) sits completely outside the pink/gold/cream palette, breaking cohesion at a key moment; no sticky/blurred navbar or mobile hamburger; flat single-tone borders with no gradient accents or hover details.

## Verdict

With Synapse wins decisively on visual design — real typography, a full color system, and layered polish versus system fonts and a flat template look.
