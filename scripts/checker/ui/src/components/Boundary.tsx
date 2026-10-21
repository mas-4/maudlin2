// A page that fails while drawing shows what failed, and a way back, instead of a blank window
import { Component, type ReactNode } from 'react'

export class Boundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }
  static getDerivedStateFromError(error: Error) {
    return { error }
  }
  render() {
    if (!this.state.error) return this.props.children
    return (
      <main className="page not-ported">
        <div className="card">
          <h1>😬 This page broke</h1>
          <p>{this.state.error.message}</p>
          <pre className="faint" style={{ whiteSpace: 'pre-wrap' }}>{this.state.error.stack?.split('\n').slice(0, 6).join('\n')}</pre>
          <p><button className="btn" onClick={() => location.reload()}>🔄 reload</button></p>
        </div>
      </main>
    )
  }
}
