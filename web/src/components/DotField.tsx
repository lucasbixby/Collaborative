// A room's picture: a grid of soft ringed dots, like a sheet of chromatography spots, drawn from
// the room's name so every room always looks like itself. A few dots breathe slowly.
import { useMemo } from 'react'

const PALETTES = [
  ['#f2901c', '#e0457b', '#f4c61f'],
  ['#2f9e6c', '#b9d43a', '#16302b'],
  ['#2d6be0', '#35b6c9', '#7a4fd6'],
  ['#e2572b', '#f2901c', '#7b2d26'],
  ['#d13f9c', '#7a4fd6', '#f4a6c0'],
]

// A small deterministic generator (mulberry32) seeded from the name.
function generator(name: string) {
  let seed = 2166136261
  for (const char of name) seed = Math.imul(seed ^ char.charCodeAt(0), 16777619)
  return () => {
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export function DotField({ name, columns = 8, rows = 4 }: { name: string; columns?: number; rows?: number }) {
  const dots = useMemo(() => {
    const random = generator(name)
    const palette = PALETTES[Math.floor(random() * PALETTES.length)]
    return Array.from({ length: columns * rows }, (_, index) => ({
      x: (index % columns) * 20 + 10,
      y: Math.floor(index / columns) * 20 + 10,
      halo: palette[Math.floor(random() * palette.length)],
      haloSize: 4.5 + random() * 4.5,
      core: random() < 0.72 ? 1.2 + random() * 3.6 : 0,
      breathes: random() < 0.18,
      delay: random() * -9,
    }))
  }, [name, columns, rows])
  const blur = `blur-${columns}-${rows}`

  return (
    <svg className="dotfield" viewBox={`0 0 ${columns * 20} ${rows * 20}`} aria-hidden="true">
      <filter id={blur} x="-50%" y="-50%" width="200%" height="200%">
        <feGaussianBlur stdDeviation="1.6" />
      </filter>
      {dots.map((dot, index) => (
        <g
          key={index}
          className={dot.breathes ? 'dot breathes' : 'dot'}
          style={{ animationDelay: `${dot.delay}s`, transformOrigin: `${dot.x}px ${dot.y}px` }}
        >
          <circle cx={dot.x} cy={dot.y} r={dot.haloSize} fill={dot.halo} filter={`url(#${blur})`} opacity="0.85" />
          {dot.core > 0 && <circle cx={dot.x} cy={dot.y} r={dot.core} fill="var(--ink)" filter={`url(#${blur})`} />}
        </g>
      ))}
    </svg>
  )
}
