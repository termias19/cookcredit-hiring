/**
 * Shared framer-motion variants/tokens — the single source of truth for
 * animation timing and easing across the app. Import from here rather than
 * hand-rolling transition objects per screen, so motion feels consistent.
 */

export const EASE = [0.16, 1, 0.3, 1] // smooth "expo-out" — snappy start, gentle settle

export const DURATION = { fast: 0.18, base: 0.32, slow: 0.5 }

/** Whole-page crossfade/slide, keyed by route pathname in App.jsx. */
export const pageVariants = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0, transition: { duration: DURATION.base, ease: EASE } },
  exit: { opacity: 0, y: -8, transition: { duration: DURATION.fast, ease: EASE } },
}

/** Fade + rise — the default entrance for cards, sections, list rows. */
export const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: DURATION.base, ease: EASE } },
}

export const fadeIn = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { duration: DURATION.base, ease: EASE } },
}

export const scaleIn = {
  hidden: { opacity: 0, scale: 0.96 },
  show: { opacity: 1, scale: 1, transition: { duration: DURATION.base, ease: EASE } },
}

/** Reveal workspace rows together by default. A per-row delay grows with the
 * list size and makes already-loaded applicants appear to be loading slowly. */
export const staggerContainer = (stagger = 0, delayChildren = 0) => ({
  hidden: {},
  show: { transition: { staggerChildren: stagger, delayChildren } },
})

export const listItem = fadeUp

/** Spread into a motion element's props for a tactile press. */
export const tapScale = { scale: 0.97 }

/** Spread into `whileHover` on a card for a subtle lift. */
export const hoverLift = { y: -4, boxShadow: '0 16px 32px rgba(18,63,52,0.12)' }

/** Spread into `whileHover`/`whileTap` on a primary button. */
export const buttonPress = { whileHover: { scale: 1.02 }, whileTap: { scale: 0.97 } }
