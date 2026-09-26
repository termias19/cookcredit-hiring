/**
 * Mise design tokens — the single source of truth for the editorial /
 * minimal look (warm paper, Cormorant serif headings, thin sharp-cornered
 * cards, uppercase letter-spaced eyebrow labels).
 *
 * These names map 1:1 to the raw hex values scattered as inline styles
 * across the screens. New screens should import from here; existing screens
 * migrate incrementally — same values, so a swap is behavior-preserving.
 */

export const colors = {
  // surfaces
  paper:    '#FEFDFB',   // app background (warm off-white)
  surface:  '#FFFFFF',   // cards / sheets
  surfaceAlt:'#F8F7F4',  // subtle raised panel
  wash:     '#F5F5F5',   // inset / disabled fill

  // ink (text) — high → low emphasis
  ink:       '#1A1A1A',  // primary text & headings
  inkMuted:  '#555555',  // secondary text
  inkSubtle: '#777777',  // captions / metadata
  inkFaint:  '#999999',  // placeholder / disabled
  inkGhost:  '#AAAAAA',  // hairline labels

  // lines
  border:     '#E5E5E5', // standard 1px card/input border
  borderSoft: '#F0F0F0', // internal dividers

  // brand — deep trust teal (a household-help marketplace: calm, clean, reliable)
  brand:     '#1F6F5C',
  brandDeep: '#123F34',
  brandSoft: '#5FA396',

  // accents
  gold:      '#C9A227',  // verification / trust badges
  goldDeep:  '#96741A',
  goldLight: '#F4E9C6',
  slate:     '#3B5166',  // secondary accent (scheduling, calm UI chrome)
  slateDeep: '#22303D',

  // semantic
  success:   '#2E7D32',
  danger:    '#D32F2F',
  dangerDark:'#C53030',

  // neutral warm greys (replaces the old food-context brown group)
  neutralWarm:     '#6B6259',
  neutralWarmDeep: '#463F38',
}

export const font = {
  // headings / display
  serif: "'Cormorant Garamond', Georgia, serif",
  // body / UI — native stack
  sans: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
}

export const space = {
  xs: '4px', sm: '8px', md: '16px', lg: '24px', xl: '32px', xxl: '48px',
}

export const radius = {
  none: '0px',   // the editorial look is sharp-cornered by default
  sm: '4px', md: '8px', pill: '999px',
}

export const border = {
  hairline: `1px solid ${colors.border}`,
  soft: `1px solid ${colors.borderSoft}`,
}

/** Composed style fragments for the recurring patterns. Spread into `style`. */
export const styles = {
  // uppercase letter-spaced eyebrow label
  eyebrow: {
    fontFamily: font.sans,
    fontSize: '11px',
    fontWeight: 600,
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
    color: colors.inkSubtle,
  },
  // serif heading
  heading: {
    fontFamily: font.serif,
    fontWeight: 500,
    color: colors.ink,
    lineHeight: 1.15,
  },
  // thin sharp-cornered white card
  card: {
    background: colors.surface,
    border: border.hairline,
    borderRadius: radius.none,
  },
}

export default { colors, font, space, radius, border, styles }
