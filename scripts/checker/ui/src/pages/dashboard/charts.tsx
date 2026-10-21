// The dashboard's two charts, stacked bars and lines over time, as plain SVG. Each is drawn at its box's real width
// (a fixed drawing shrunk into a card made its labels unreadable) and drawn again when that width changes: a window
// resized, a phone turned.
import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'

export const PALETTE = ['#3a86ff', '#ffc400', '#00c2a8', '#ff4d6d', '#8a5cff', '#2ec27e', '#ff8c42', '#7a7a8c', '#00a6fb', '#c77dff']
const DANGER = '#ff4d6d'

/** "2026-10-21" as "10/21" */
export const short = (d: string) => d.slice(5).replace('-', '/')

/** The box's width, kept up to date; 0 until it is laid out */
function useWidth() {
  const ref = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    setWidth(Math.round(el.clientWidth))
    let timer: number | undefined
    const ro = new ResizeObserver(() => {
      clearTimeout(timer)
      timer = window.setTimeout(() => setWidth(Math.round(el.clientWidth)), 150)
    })
    ro.observe(el)
    return () => {
      clearTimeout(timer)
      ro.disconnect()
    }
  }, [])
  return [ref, width] as const
}

/** A chart's box: measures itself and hands the width (240 at the least, so a narrow phone scrolls) to the drawing */
function Plot({ draw }: { draw: (W: number) => ReactNode }) {
  const [ref, width] = useWidth()
  return <div className="dash-plot" ref={ref}>{width > 0 && draw(Math.max(240, width))}</div>
}

function Key({ names, colorOf }: { names: string[]; colorOf: (n: string, k: number) => string }) {
  return <div className="dash-key">{names.map((n, k) => <span key={n}><i style={{ background: colorOf(n, k) }} />{n}</span>)}</div>
}

/** A dashed red line across the chart with its label at the right end: a limit to stay under */
function Limit({ x1, x2, y, label }: { x1: number; x2: number; y: number; label: string }) {
  return (
    <g className="dash-limit">
      <line x1={x1} x2={x2} y1={y} y2={y} stroke={DANGER} strokeDasharray="4 3" strokeWidth={1.5} />
      <text x={x2 - 2} y={y - 3} textAnchor="end">{label}</text>
    </g>
  )
}

export type Series = Record<string, Record<string, number>>
export interface BarOpts {
  colors?: Record<string, string>
  line?: number // a limit drawn across, in the bars' units
  lineLabel?: string
  max?: number // the scale reaches at least this high
  fmt?: (label: string) => string // the label under a bar (default: the day as 10/21)
  tickWidth?: number // room each label under the bars needs
  h?: number
  key?: boolean // a key even for one series
}

/** Stacked bars, one per label: series = {name: {label: n}} */
export function Bars({ labels, series, opts = {} }: { labels: string[]; series: Series; opts?: BarOpts }) {
  const names = Object.keys(series)
  const colorOf = (n: string, k: number) => opts.colors?.[n] ?? PALETTE[k % PALETTE.length]
  const draw = (W: number) => {
    const H = opts.h ?? 190, pad = 40, bw = (W - pad) / Math.max(1, labels.length)
    const totals = labels.map((l) => names.reduce((t, n) => t + (series[n][l] || 0), 0))
    const peak = Math.max(1, opts.max ?? 0, ...totals)
    const every = Math.ceil(labels.length / Math.max(2, Math.floor((W - pad) / (opts.tickWidth ?? 52))))
    return (
      <svg className="dash-chart" viewBox={`0 0 ${W} ${H + 18}`} style={{ minWidth: 240 }}>
        <line x1={pad} x2={W} y1={H / 2} y2={H / 2} className="dash-grid-line" />
        {labels.map((l, i) => {
          let y = H
          return (
            <g key={l}>
              {names.map((n, k) => {
                const v = series[n][l] || 0, h = (v / peak) * (H - 10)
                y -= h
                return v ? (
                  <rect key={n} x={pad + i * bw + 1} y={y} width={Math.max(1, bw - 2)} height={h} rx={2} fill={colorOf(n, k)}>
                    <title>{`${l} · ${n}: ${v.toLocaleString()}`}</title>
                  </rect>
                ) : null
              })}
              {i % every === 0 && <text x={pad + i * bw + bw / 2} y={H + 13} textAnchor="middle">{opts.fmt ? opts.fmt(l) : short(l)}</text>}
            </g>
          )
        })}
        {opts.line != null && <Limit x1={pad} x2={W} y={H - (opts.line / peak) * (H - 10)} label={opts.lineLabel ?? ''} />}
        <text x={pad - 6} y={14} textAnchor="end">{peak.toLocaleString()}</text>
        <text x={pad - 6} y={H} textAnchor="end">0</text>
        <line x1={pad} x2={W} y1={H} y2={H} stroke="#1f1f2e" strokeWidth={1.5} />
        <line x1={pad} x2={pad} y1={4} y2={H} stroke="#ccc" />
      </svg>
    )
  }
  return (
    <>
      <Plot draw={draw} />
      {(names.length > 1 || opts.key) && <Key names={names} colorOf={colorOf} />}
    </>
  )
}

/** One series of bars, with no key */
export function OneBars({ labels, values, name }: { labels: string[]; values: Record<string, number>; name: string }) {
  return <Bars labels={labels} series={{ [name]: values }} />
}

export type Point = { at: string } & Record<string, unknown>
/** [key, top of the scale, colour, bottom of the scale (0)] */
export type LineSpec = [string, number, string, number?]
export interface LineOpts {
  danger?: [number, number, string] // a limit: [value, top of its scale, label]
  scale?: boolean // the scale's top and bottom written at the left
  empty?: string // what to say when there are no readings
}

/** Lines over time: points = [{at, value…}], one line per spec; a missing value breaks its line */
export function Lines({ points, lines, opts = {} }: { points: Point[]; lines: LineSpec[]; opts?: LineOpts }) {
  if (!points.length) return <p className="dash-sub">{opts.empty ?? 'no readings yet'}</p>
  const val = (p: Point, key: string) => (typeof p[key] === 'number' ? (p[key] as number) : null)
  const draw = (W: number) => {
    const H = 170, n = points.length
    const x = (i: number) => (n === 1 ? W / 2 : (i / (n - 1)) * W)
    const ticks = [...new Set([0, Math.floor(n / 4), Math.floor(n / 2), Math.floor((3 * n) / 4), n - 1])]
    return (
      <svg className="dash-chart" viewBox={`0 0 ${W} ${H + 18}`} style={{ minWidth: 240 }}>
        <line x1={0} x2={W} y1={H / 2} y2={H / 2} className="dash-grid-line" />
        <line x1={0} x2={W} y1={H} y2={H} stroke="#1f1f2e" strokeWidth={1.5} />
        {lines.map(([key, max, color, min = 0]) => {
          const y = (v: number) => H - ((v - min) / (max - min)) * (H - 6)
          let d = '', up = true
          points.forEach((p, i) => {
            const v = val(p, key)
            if (v == null) { up = true; return }
            d += `${up ? 'M' : 'L'}${x(i)},${y(v)}`
            up = false
          })
          return (
            <g key={key}>
              <path d={d} fill="none" stroke={color} strokeWidth={2} />
              {n <= 60 && points.map((p, i) => {
                const v = val(p, key)
                return v == null ? null : (
                  <circle key={i} cx={x(i)} cy={y(v)} r={3} fill={color} stroke="#1f1f2e" strokeWidth={0.75}>
                    <title>{`${p.at.replace('T', ' ')} · ${key}: ${v}`}</title>
                  </circle>
                )
              })}
              {opts.scale && <><text x={2} y={12}>{max}</text><text x={2} y={H - 2}>{min}</text></>}
            </g>
          )
        })}
        {opts.danger && <Limit x1={0} x2={W} y={H - (opts.danger[0] / opts.danger[1]) * (H - 6)} label={opts.danger[2]} />}
        {ticks.map((i) => (
          <text key={i} x={(i / Math.max(1, n - 1)) * W} y={H + 13} textAnchor={i ? (i === n - 1 ? 'end' : 'middle') : 'start'}>
            {points[i].at.slice(5).replace('T', ' ')}
          </text>
        ))}
      </svg>
    )
  }
  return (
    <>
      <Plot draw={draw} />
      <Key names={lines.map(([k]) => k)} colorOf={(_, k) => lines[k][2]} />
    </>
  )
}
