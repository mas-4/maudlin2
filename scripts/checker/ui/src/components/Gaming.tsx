// 🎮 gaming mode in the nav (Oct 22, the person: "i need a gaming mode"): the card and the machine to the person, the
// worker and experiments waiting and the hourly runs only scraping until it's turned off (app/gaming.py; 12 hours
// at most)
import { postJSON } from '../lib/api'
import { client, useJSON } from '../lib/queries'
import { toast } from './Feedback'

interface GamingState { on: boolean; until: number | null; text: string }

export function Gaming() {
  const { data } = useJSON<GamingState>('/gaming.json', undefined, { refetchInterval: 60_000 })
  const on = !!data?.on
  const flip = async () => {
    try {
      const now = await postJSON<GamingState>('/gaming', { on: !on })
      client.setQueryData(['/gaming.json', {}], now)
      toast(now.on ? '🎮 Gaming mode on: the worker and experiments wait, the hourly runs only scrape (12 hours at most)' : '🎮 Gaming mode off: back to work')
    } catch (e) {
      toast('😬 couldn’t switch gaming mode: ' + (e as Error).message, true)
    }
  }
  return (
    <button className={'nav-gaming' + (on ? ' on' : '')} title={data?.text ?? 'gaming mode: the card and the machine to you'} onClick={() => void flip()}>
      🎮{on ? ' gaming' : ''}
    </button>
  )
}
