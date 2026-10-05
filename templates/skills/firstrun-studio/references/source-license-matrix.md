# Source and license matrix

Research snapshot: 2026-09-01.

| Source | Reuse class | License / constraint | FirstRun use |
|---|---|---|---|
| shadcn/ui | Source/primitives may be adapted | MIT; verify repository notice/version at use time | Accessible form/dialog/button primitives and implementation patterns |
| gilbarbara/react-joyride | Source/package may be used subject to license | MIT; verify current release/peer compatibility | Guided tour/coach-mark primitive when a tour is actually justified |
| uixmat/onborda | Source/package may be used subject to license | package metadata declares MIT; verify current release | Next.js/Framer Motion onboarding/product-tour primitive |
| Userflow | Pattern reference only | Proprietary product/site | Onboarding strategy, activation, personalization, checklist/resource-center patterns |
| Lovable | Pattern/process reference only | Proprietary product/site | Design-system discipline, beautiful defaults, prompt-to-design-brief process |
| Dribbble shots | Visual inspiration only | Creator-owned visuals; rights vary | Composition/motion/style ideation only; never copy assets or exact screen |

## License-first rule

Before copying code:
1. identify the exact repository/package and version
2. inspect LICENSE/package metadata
3. record the license
4. comply with attribution/notice obligations
5. prefer dependency installation or small adapted primitives over wholesale repository copying
6. scan for incompatible bundled assets/fonts/icons with separate licenses

If license is missing/unclear, treat the code as reference-only.

## Provenance note format

For any reused open-source implementation:
- source URL:
- version/commit:
- license:
- files/concepts adapted:
- local changes:
- attribution/notice action:

Never describe a proprietary site scrape as "open source."
