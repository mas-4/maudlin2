import type { Page } from '../lib/routes'

export function NotPorted({ page }: { page: Page }) {
  return (
    <main className="page not-ported">
      <div className="card">
        <h1>
          {page.emoji} {page.name}
        </h1>
        <p>This page isn’t in the new checker yet. The old one still works:</p>
        <p>
          <a className="btn" href={page.old}>
            open the old {page.name} →
          </a>
        </p>
      </div>
    </main>
  )
}
