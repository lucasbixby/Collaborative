// The page's background: a large field of soft dots behind the left two thirds of the window,
// starting below the header (or, signed out, below the name). Each dot swells and
// shrinks a little, each row rides up and down a beat after the one above so the field moves
// like a wave, and the whole field drifts slowly round the colour wheel. The dots are shades of
// one hue, so as it turns they stay a family.
import type { CSSProperties } from 'react'

const COLUMNS = 6
const ROWS = 5
const SHADES = [
  'hsl(322 78% 62%)',
  'hsl(300 62% 70%)',
  'hsl(338 85% 76%)',
  'hsl(284 58% 60%)',
  'hsl(318 55% 84%)',
]

// Fixed pseudo-random numbers, so the field is the same on every launch.
function sequence(seed: number) {
  return () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) | 0
    return (seed >>> 0) / 4294967296
  }
}

const random = sequence(7)
const DOTS = Array.from({ length: COLUMNS * ROWS }, (_, index) => {
  const column = index % COLUMNS
  const row = Math.floor(index / COLUMNS)
  return {
    left: `${((column + 0.5) / COLUMNS) * 100}%`,
    top: `${((row + 0.5) / ROWS) * 100}%`,
    size: 7 + random() * 7,
    shade: SHADES[Math.floor(random() * SHADES.length)],
    core: random() < 0.6 ? 0.25 + random() * 0.55 : 0,
    swell: 5 + random() * 5,
    // Later rows, and to a lesser degree later columns, start later: the wave travels.
    delay: -(row * 1.1 + column * 0.35),
  }
})

export function BackgroundField({ belowWordmark = false }: { belowWordmark?: boolean }) {
  return (
    <div className={belowWordmark ? 'field below-wordmark' : 'field'} aria-hidden="true">
      {DOTS.map((dot, index) => (
        <span
          key={index}
          className="field-dot"
          style={
            {
              left: dot.left,
              top: dot.top,
              '--size': `${dot.size}vmax`,
              '--shade': dot.shade,
              '--core': dot.core,
              '--swell': `${dot.swell}s`,
              '--delay': `${dot.delay}s`,
            } as CSSProperties
          }
        >
          <i />
        </span>
      ))}
    </div>
  )
}
