// The flow chart: a row per news story, a day 110px wide at least (scroll sideways for more). The pale bar is the
// story's life on the front pages; each dot a filing on the day it was told, shaped by its source and coloured by its
// motif's genre. Story names stay pinned on the left and the days on top while the chart scrolls both ways.
import { memo, useEffect, useLayoutEffect, useMemo, useRef, useState, type MouseEvent } from 'react'
import * as d3 from 'd3'
import { day, genreColor, type FlowData, type Filing, type Row, type Source } from './data'

const ROW = 24, PAD = 30, PXDAY = 110, STEP = 9 // a row's height, the axis's, a day's least width, the gap between same-day dots

const SHAPE: Record<Source, d3.SymbolType> = {
  posts: d3.symbolCircle, 'fact-check': d3.symbolSquare, shows: d3.symbolTriangle, 'focus group': d3.symbolDiamond,
}
const paths = new Map<string, string>()
function mark(source: Source, plain: boolean): string { // a plain-reporting dot is drawn smaller: it is the baseline
  const k = source + plain
  if (!paths.has(k)) paths.set(k, d3.symbol(SHAPE[source] ?? d3.symbolCircle, plain ? 50 : 80)() ?? '')
  return paths.get(k)!
}

const tickDay = d3.timeFormat('%a %b %-d')

export interface Tip { x: number; y: number; f: Filing; s: Row }

interface Props {
  data: FlowData
  rows: Row[]
  picked: string | null
  story: number | null
  onMotif: (id: string) => void
  onStory: (id: number) => void
  onTip: (t: Tip | null) => void
}

export const Timeline = memo(function Timeline({ data, rows, picked, story, onMotif, onStory, onTip }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  useLayoutEffect(() => {
    const el = box.current!
    const ro = new ResizeObserver(() => setWidth(el.clientWidth))
    ro.observe(el)
    setWidth(el.clientWidth)
    return () => ro.disconnect()
  }, [])
  const label = width && width < 640 ? 150 : 330 // story names take less room on a phone

  const geo = useMemo(() => {
    const dates = rows.flatMap((s) => [day(s.first), day(s.last), ...s.fs.map((f) => day(f.date))]).filter((d): d is Date => !!d)
    if (!dates.length) return null
    const d0 = d3.timeDay.offset(d3.min(dates)!, -1), d1 = d3.timeDay.offset(d3.max(dates)!, 1)
    const W = Math.max((width || 1000) - label - 8, d3.timeDay.count(d0, d1) * PXDAY)
    const x = d3.scaleTime().domain([d0, d1]).range([16, W - 16])
    const midnights = d3.timeDay.range(d0, d1)
    return { d0, d1, W, H: rows.length * ROW + 10, x, midnights }
  }, [rows, width, label])

  // open on the latest days, once; following a motif goes back to the top, where its stories now are
  const scrolled = useRef(false)
  useLayoutEffect(() => {
    if (scrolled.current || !geo || !width) return
    box.current!.scrollLeft = box.current!.scrollWidth
    scrolled.current = true
  }, [geo, width])
  useEffect(() => {
    if (picked) box.current!.scrollTop = 0
  }, [picked])

  const has = (s: Row) => !picked || s.fs.some((f) => f.motif === picked)
  const now = new Date()
  const tipAt = (ev: MouseEvent, f: Filing, s: Row) => onTip({ x: ev.clientX, y: ev.clientY, f, s })

  return (
    <div className="flow-card flow-chart" ref={box}>
      {!geo ? <p className="flow-none">🦗 nothing matches: loosen the search or tick more sources</p> : (
        <div className="flow-grid">
          {/* flex rows, not a grid: a sticky grid item can't leave its own cell, so the names would scroll away */}
          <div className="flow-head">
          <div className="flow-corner" style={{ height: PAD, width: label }} />
          <svg className="flow-axis" width={geo.W} height={PAD}>
            {geo.midnights.map((d) => (
              <g key={+d}>
                <line x1={geo.x(d)} x2={geo.x(d)} y1={PAD - 10} y2={PAD} />
                <text x={geo.x(d3.timeHour.offset(d, 12))} y={PAD - 10} textAnchor="middle">{tickDay(d)}</text>
              </g>
            ))}
          </svg>
          </div>
          <div className="flow-body">
          <div className="flow-labels" style={{ width: label }}>
            {rows.map((s) => (
              <button key={s.id} type="button" title={s.label} style={{ height: ROW, lineHeight: ROW + 'px' }}
                className={'flow-lab' + (s.id === story ? ' on' : '') + (has(s) ? '' : ' flow-dim')} onClick={() => onStory(s.id)}>
                {s.label}
              </button>
            ))}
          </div>
          <svg className="flow-plot" width={geo.W} height={geo.H}>
            <g className="flow-daygrid">
              {geo.midnights.map((d) => <line key={+d} x1={geo.x(d)} x2={geo.x(d)} y1={0} y2={geo.H} />)}
            </g>
            {now >= geo.d0 && now <= geo.d1 && <line className="flow-today" x1={geo.x(now)} x2={geo.x(now)} y1={0} y2={geo.H}><title>now</title></line>}
            {rows.map((s, i) => {
              const seen: Record<string, number> = {}
              const a = day(s.first), b = day(s.last)
              return (
                <g key={s.id} transform={`translate(0,${i * ROW})`} className={has(s) ? undefined : 'flow-dim'}>
                  {a && b && (
                    <rect className="flow-life" x={geo.x(a)} width={Math.max(4, geo.x(b) - geo.x(a) + 6)} y={ROW / 2 - 4} height={8} rx={4}>
                      <title>{`${s.label}: in the news ${s.first!.slice(0, 10)} to ${s.last!.slice(0, 10)}`}</title>
                    </rect>
                  )}
                  {s.fs.map((f, j) => {
                    const at = day(f.date)
                    if (!at) return null
                    const n = (seen[f.date] = (seen[f.date] ?? 0) + 1) - 1 // dots on the same day sit side by side
                    return (
                      <path key={j} d={mark(f.source, f.plain)} transform={`translate(${geo.x(at) + n * STEP},${ROW / 2})`}
                        className={'flow-dot' + (f.plain ? ' plain' : '') + (f.checked ? '' : ' unchecked') + (picked === f.motif ? ' on' : '')}
                        fill={f.plain ? '#fff' : genreColor(data.genres, data.motifs[f.motif]?.genre)}
                        onMouseEnter={(ev) => tipAt(ev, f, s)} onMouseMove={(ev) => tipAt(ev, f, s)} onMouseLeave={() => onTip(null)}
                        onClick={() => onMotif(f.motif)} />
                    )
                  })}
                </g>
              )
            })}
          </svg>
          </div>
        </div>
      )}
    </div>
  )
})
