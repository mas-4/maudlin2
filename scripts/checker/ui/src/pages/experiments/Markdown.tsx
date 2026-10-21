// A small Markdown reader for the experiment papers (~/maudlin-data/papers): headings, paragraphs, lists (nested by
// indentation), tables, quotes, code blocks, rules, and inline code, bold, italics and links. It builds React elements,
// never HTML strings, so whatever a paper says is drawn as text; links go out only to http(s), mailto or this site.
import type { ReactNode } from 'react'

type Align = 'left' | 'center' | 'right' | undefined
interface Item { text: string; sub: List[] }
interface List { ordered: boolean; start: number; indent: number; items: Item[] }
type Block =
  | { t: 'h'; level: number; text: string }
  | { t: 'p'; text: string }
  | { t: 'code'; text: string }
  | { t: 'quote'; blocks: Block[] }
  | { t: 'hr' }
  | { t: 'table'; align: Align[]; head: string[] | null; rows: string[][] }
  | { t: 'list'; list: List }

const HEADING = /^ {0,3}(#{1,6})\s+(.*?)(?:\s+#+)?\s*$/
const FENCE = /^ {0,3}(```|~~~)/
const HR = /^ {0,3}([-*_])(?:\s*\1){2,}\s*$/
const ITEM = /^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$/
const QUOTE = /^ {0,3}>\s?(.*)$/
const SEPARATOR = /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/
const isRow = (l: string) => l.trimStart().startsWith('|')

/** Splits a table row into its cells: pipes inside `code` or escaped as \| stay in the cell */
function cells(row: string): string[] {
  let s = row.trim()
  if (s.startsWith('|')) s = s.slice(1)
  if (s.endsWith('|') && !s.endsWith('\\|')) s = s.slice(0, -1)
  const out: string[] = []
  let cur = ''
  let code = false
  for (let k = 0; k < s.length; k++) {
    const c = s[k]
    if (c === '\\' && s[k + 1] === '|') {
      cur += '|'
      k++
      continue
    }
    if (c === '`') code = !code
    if (c === '|' && !code) {
      out.push(cur.trim())
      cur = ''
      continue
    }
    cur += c
  }
  out.push(cur.trim())
  return out
}

function alignOf(cell: string): Align {
  const l = cell.startsWith(':'), r = cell.endsWith(':')
  return l && r ? 'center' : r ? 'right' : l ? 'left' : undefined
}

/** A line that starts a block of its own and so ends a paragraph. An ordered item interrupts only from 1, so a
 * sentence that happens to start "2026. " stays in its paragraph */
function interrupts(l: string): boolean {
  if (HEADING.test(l) || FENCE.test(l) || HR.test(l) || isRow(l) || QUOTE.test(l)) return true
  const m = ITEM.exec(l)
  return !!m && m[1].length < 4 && (!/\d/.test(m[2]) || parseInt(m[2]) === 1)
}

/** A list from line i on, nesting items by their indentation; returns it and the line after it */
function parseList(lines: string[], i: number): [List, number] {
  const stack: List[] = []
  let last: Item | null = null
  while (i < lines.length) {
    const l = lines[i]
    if (!l.trim()) {
      // a blank line: the list goes on only if what follows is another item or indented under one
      const next = lines[i + 1]
      if (next !== undefined && (ITEM.test(next) || /^\s{2,}\S/.test(next))) {
        i++
        continue
      }
      break
    }
    const m = ITEM.exec(l)
    if (m && !HR.test(l)) {
      const indent = m[1].replace(/\t/g, '    ').length
      const ordered = /\d/.test(m[2])
      const item: Item = { text: m[3], sub: [] }
      const start = ordered ? parseInt(m[2]) : 1
      while (stack.length > 1 && indent < stack[stack.length - 1].indent) stack.pop()
      const top = stack[stack.length - 1]
      if (!top) stack.push({ ordered, start, indent, items: [item] })
      else if (indent > top.indent) {
        const sub: List = { ordered, start, indent, items: [item] }
        top.items[top.items.length - 1].sub.push(sub)
        stack.push(sub)
      } else if (stack.length === 1 && ordered !== top.ordered) break // a list of the other kind starts a new list
      else top.items.push(item)
      last = item
      i++
      continue
    }
    if (HEADING.test(l) || FENCE.test(l) || HR.test(l) || isRow(l) || (QUOTE.test(l) && !/^\s/.test(l))) break
    if (!last) break
    last.text += ' ' + l.trim() // the item's text, wrapped onto the next line
    i++
  }
  return [stack[0], i]
}

function parseBlocks(lines: string[]): Block[] {
  const out: Block[] = []
  let i = 0
  while (i < lines.length) {
    const l = lines[i]
    if (!l.trim()) {
      i++
      continue
    }
    let m: RegExpExecArray | null
    if ((m = FENCE.exec(l))) {
      const fence = m[1]
      const body: string[] = []
      i++
      while (i < lines.length && !lines[i].trim().startsWith(fence)) body.push(lines[i++])
      i++
      out.push({ t: 'code', text: body.join('\n') })
      continue
    }
    if ((m = HEADING.exec(l))) {
      out.push({ t: 'h', level: m[1].length, text: m[2] })
      i++
      continue
    }
    if (HR.test(l)) {
      out.push({ t: 'hr' })
      i++
      continue
    }
    if (QUOTE.test(l)) {
      const body: string[] = []
      while (i < lines.length && (m = QUOTE.exec(lines[i]))) {
        body.push(m[1])
        i++
      }
      out.push({ t: 'quote', blocks: parseBlocks(body) })
      continue
    }
    if (isRow(l)) {
      const rows: string[] = []
      while (i < lines.length && isRow(lines[i])) rows.push(lines[i++])
      const headed = rows.length > 1 && SEPARATOR.test(rows[1])
      const align = headed ? cells(rows[1]).map(alignOf) : []
      const body = rows.filter((r, k) => !(headed && k <= 1) && !SEPARATOR.test(r)).map(cells)
      out.push({ t: 'table', align, head: headed ? cells(rows[0]) : null, rows: body })
      continue
    }
    if (ITEM.test(l)) {
      const [list, next] = parseList(lines, i)
      out.push({ t: 'list', list })
      i = next
      continue
    }
    const para: string[] = [l.trim()]
    i++
    while (i < lines.length && lines[i].trim() && !interrupts(lines[i])) para.push(lines[i++].trim())
    out.push({ t: 'p', text: para.join(' ') })
  }
  return out
}

// Inline marks, earliest first; at one place the first that fits wins (so ** is bold before * is italics)
const INLINE = new RegExp(
  [
    /`([^`]+)`/.source, // 1: code
    /\[([^\]]+)\]\(([^()\s]+)\)/.source, // 2, 3: a link's words and address
    /\*\*(?=\S)(.+?)(?<=\S)\*\*/.source, // 4: bold
    /(?<!\w)__(?=\S)(.+?)(?<=\S)__(?!\w)/.source, // 5: bold
    /(?<![\w*])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![\w*])/.source, // 6: italics
    /(?<![\w_])_(?=[^\s_])(.+?)(?<=[^\s_])_(?![\w_])/.source, // 7: italics (not inside file_names)
    /(https?:\/\/[^\s<>]*[^\s<>.,;:!?'")\]])/.source, // 8: a bare address
  ].join('|'),
  'g',
)

/** An address safe to link to: the web, mail, or a path on this site */
function safeHref(h: string): string | null {
  return /^(https?:|mailto:)/i.test(h) || /^[/#]/.test(h) ? h : null
}

function link(href: string, words: ReactNode, key: string): ReactNode {
  const safe = safeHref(href)
  if (!safe) return <span key={key}>{words}</span>
  const out = /^https?:/i.test(safe)
  return (
    <a key={key} href={safe} {...(out ? { target: '_blank', rel: 'noopener noreferrer' } : {})}>
      {words}
    </a>
  )
}

function inline(text: string, key = 'i'): ReactNode[] {
  const out: ReactNode[] = []
  let at = 0
  let n = 0
  for (const m of text.matchAll(INLINE)) {
    const k = `${key}.${n++}`
    if (m.index > at) out.push(text.slice(at, m.index))
    if (m[1] !== undefined) out.push(<code key={k}>{m[1]}</code>)
    else if (m[2] !== undefined) out.push(link(m[3], inline(m[2], k), k))
    else if (m[4] !== undefined || m[5] !== undefined) out.push(<b key={k}>{inline(m[4] ?? m[5], k)}</b>)
    else if (m[6] !== undefined || m[7] !== undefined) out.push(<i key={k}>{inline(m[6] ?? m[7], k)}</i>)
    else if (m[8] !== undefined) out.push(link(m[8], m[8], k))
    at = m.index + m[0].length
  }
  if (at < text.length) out.push(text.slice(at))
  return out
}

function ListView({ list, k }: { list: List; k: string }) {
  const items = list.items.map((it, n) => (
    <li key={n}>
      {inline(it.text, `${k}.${n}`)}
      {it.sub.map((s, j) => (
        <ListView key={j} list={s} k={`${k}.${n}.${j}`} />
      ))}
    </li>
  ))
  return list.ordered ? <ol start={list.start === 1 ? undefined : list.start}>{items}</ol> : <ul>{items}</ul>
}

function render(blocks: Block[], key: string): ReactNode[] {
  return blocks.map((b, n) => {
    const k = `${key}.${n}`
    switch (b.t) {
      case 'h': {
        // the page's own headings are h1 and h2, so a paper's headings start at h3
        const Tag = `h${Math.min(6, b.level + 2)}` as 'h3'
        return <Tag key={k} className={`ex-md-h${b.level}`}>{inline(b.text, k)}</Tag>
      }
      case 'p':
        return <p key={k}>{inline(b.text, k)}</p>
      case 'code':
        return <pre key={k}><code>{b.text}</code></pre>
      case 'quote':
        return <blockquote key={k}>{render(b.blocks, k)}</blockquote>
      case 'hr':
        return <hr key={k} />
      case 'list':
        return <ListView key={k} list={b.list} k={k} />
      case 'table':
        return (
          <div key={k} className="ex-md-table">
            <table>
              {b.head && (
                <thead>
                  <tr>{b.head.map((c, j) => <th key={j} style={{ textAlign: b.align[j] }}>{inline(c, `${k}.h${j}`)}</th>)}</tr>
                </thead>
              )}
              <tbody>
                {b.rows.map((r, j) => (
                  <tr key={j}>{r.map((c, x) => <td key={x} style={{ textAlign: b.align[x] }}>{inline(c, `${k}.${j}.${x}`)}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
        )
    }
  })
}

export function Markdown({ text }: { text: string }) {
  return <div className="ex-md">{render(parseBlocks(text.replace(/\r\n?/g, '\n').split('\n')), 'b')}</div>
}
