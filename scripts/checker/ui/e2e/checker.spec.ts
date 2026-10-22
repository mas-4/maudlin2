// The checker as the person uses it, in a real browser, on a copy of the data (playwright.config.ts): every page draws,
// the old addresses lead to the new pages, and the work of the 🎯 judge tab saves, comes back with undo, and never
// refuses a press. Written against whatever the copy holds, so a test that needs something there (a sure claim, a
// misfit) skips when there's none.
import { expect, test, type Page } from '@playwright/test'

/** A part's count in the inbox (the number after its name), or null when it shows none */
async function count(page: Page, part: string): Promise<number | null> {
  const i = page.locator('.parts .part', { hasText: part }).locator('i')
  return (await i.count()) ? Number(await i.innerText()) : null
}

async function judge(page: Page, part = 'claims to judge') {
  await page.goto('/ui/workbench')
  await expect(page.locator('.tree-pane .row').first()).toBeVisible()
  await page.locator('.inbox-pane .tabs .tab', { hasText: 'judge' }).click()
  await page.locator('.parts .part', { hasText: part }).click()
}

test('the old addresses lead to the React pages', async ({ page }) => {
  for (const [old, now] of [['/', '/ui/workbench'], ['/motif-workbench', '/ui/workbench'], ['/motif-map', '/ui/map'], ['/entities', '/ui/names']]) {
    await page.goto(old)
    await expect(page).toHaveURL(new RegExp(now.replace(/\//g, '\\/') + '$'))
  }
})

test('every page draws, with no error', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
  const pages: [string, string][] = [['workbench', '.tree-pane .row'], ['map', '.mm svg g.mm-node'], ['dashboard', '.dash-title'],
    ['experiments', '.ex-head'], ['flow', '.flow-title'], ['live', '.lv'], ['labels', '.lb-foot'], ['names', 'text=Suggested merges']]
  for (const [path, ready] of pages) {
    await page.goto(`/ui/${path}`)
    await expect(page.locator(ready).first(), path).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText('This page broke'), path).toHaveCount(0)
  }
  expect(errors).toEqual([])
})

test('the inbox has five tabs, and each reopens on the part last used', async ({ page }) => {
  await judge(page)
  await expect(page.locator('.inbox-pane .tabs .tab')).toHaveText([/judge/, /shape/, /tidy/, /find/, /stats/])
  await page.locator('.parts .part', { hasText: 'misfits' }).click()
  await page.locator('.inbox-pane .tabs .tab', { hasText: 'tidy' }).click()
  await expect(page.locator('.parts .part.on')).toContainText('pairs')
  await page.locator('.inbox-pane .tabs .tab', { hasText: 'judge' }).click()
  await expect(page.locator('.parts .part.on')).toContainText('misfits')
})

test('a verdict saves, the next claim comes up, and undo takes it back', async ({ page }) => {
  await judge(page)
  const before = await count(page, 'claims to judge')
  test.skip(!before, 'no claim waiting in the copy')
  const first = await page.locator('.bigtext').innerText()
  await page.keyboard.press('y')
  await expect(page.locator('.bigtext')).not.toHaveText(first) // the next claim, at once
  await expect(page.locator('.toast')).toContainText('fit')
  await expect.poll(() => count(page, 'claims to judge')).toBe(before! - 1)
  await page.locator('.nav-undo button').click()
  await expect(page.locator('.toast')).toContainText('undid')
  await expect.poll(() => count(page, 'claims to judge')).toBe(before)
})

test('quick presses are never refused', async ({ page }) => {
  await judge(page)
  const before = await count(page, 'claims to judge')
  test.skip(!before || before < 3, 'fewer than three claims waiting in the copy')
  for (let n = 0; n < 3; n++) await page.keyboard.press('y')
  await expect(page.locator('.nav-saving')).toHaveCount(0, { timeout: 20_000 }) // every change saved
  await expect(page.getByText('still saving')).toHaveCount(0)
  await expect.poll(() => count(page, 'claims to judge')).toBe(before! - 3)
  for (let n = 0; n < 3; n++) {
    await page.locator('.nav-undo button').click()
    await expect(page.locator('.nav-saving')).toHaveCount(0)
  }
  await expect.poll(() => count(page, 'claims to judge')).toBe(before)
})

test('passing the sure page holds a claim with a motif unticked', async ({ page }) => {
  await judge(page, 'sure')
  const sure = await count(page, 'sure')
  test.skip(!sure, 'no sure claim in the copy')
  const held = (await count(page, 'held')) ?? 0
  await page.locator('.inbox-scroll input[type=checkbox]').first().uncheck()
  await page.locator('.inbox-scroll button', { hasText: 'pass the ticked' }).click()
  await expect(page.locator('.toast')).toContainText('passed')
  await expect.poll(async () => (await count(page, 'held')) ?? 0).toBe(held + 1)
  await page.locator('.nav-undo button').click()
  await expect.poll(async () => (await count(page, 'held')) ?? 0).toBe(held)
})

test('a misfit ticked is taken out, and undo puts it back', async ({ page }) => {
  await judge(page, 'misfits')
  const misfits = await count(page, 'misfits')
  test.skip(!misfits, 'no misfit in the copy')
  await page.locator('.inbox-scroll input[type=checkbox]').first().check()
  await page.getByRole('button', { name: '✕ take out the ticked', exact: true }).click()
  await expect(page.locator('.toast')).toContainText('took out')
  await page.locator('.nav-undo button').click()
  await expect(page.locator('.toast')).toContainText('undid')
})

test('a claim dragged onto a motif offers its choices, and the folded shelf opens while dragging', async ({ page }) => {
  await judge(page)
  test.skip(!(await count(page, 'claims to judge')), 'no claim waiting in the copy')
  const fold = page.locator('.shelf-fold')
  if (!(await page.locator('.shelf.folded').count())) await fold.click()
  await expect(page.locator('.shelfboxes')).toBeHidden()
  const claim = await page.locator('.inspect .claim.big').boundingBox()
  const own = await page.locator('.inspect .motifrow .chip[data-id]').evaluateAll((cs) => cs.map((c) => (c as HTMLElement).dataset.id))
  const rows = page.locator('.tree-pane .row[data-drop]')
  let at = 0 // a motif the claim isn't in: dropping on its own offers nothing
  while (own.includes((await rows.nth(at).getAttribute('data-id')) ?? '')) at++
  const row = await rows.nth(at).boundingBox()
  await page.mouse.move(claim!.x + 30, claim!.y + 20)
  await page.mouse.down()
  await page.mouse.move(claim!.x + 60, claim!.y + 40, { steps: 5 })
  await expect(page.locator('.shelfboxes')).toBeVisible() // open over the panes, to drop on a group or genre
  await page.mouse.move(row!.x + 60, row!.y + row!.height / 2, { steps: 15 })
  await expect(page.locator('.dz-menu')).toBeVisible()
  await expect(page.locator('.dz-menu')).toContainText(/move|here too|file/)
  await page.keyboard.press('Escape')
  await page.mouse.up()
  await expect(page.locator('.dz-menu')).toHaveCount(0)
  await expect(page.locator('.shelfboxes')).toBeHidden()
})

test('a sure claim: middle-click opens it in a new tab, a plain click on the right, and it still drags', async ({ page, context }) => {
  await judge(page, 'sure')
  test.skip(!(await count(page, 'sure')), 'no sure claim in the copy')
  const link = page.locator('.sureline .claimlink').first()
  const words = await link.innerText()
  const [tab] = await Promise.all([context.waitForEvent('page'), link.click({ button: 'middle' })])
  await tab.waitForURL(/claim=/) // a new tab starts blank, then goes to the claim's address
  await expect(tab.locator('.inspect .bigtext')).toHaveText(words, { timeout: 15_000 })
  await tab.close()
  await expect(page.locator('.parts .part.on')).toContainText('sure') // the first tab stayed where it was
  await link.click()
  await expect(page.locator('.inspect .bigtext')).toHaveText(words) // a plain click: opened on the right
  await page.locator('.back').click()
  const from = await page.locator('.sureline .claimlink').first().boundingBox()
  const drop = await page.locator('.drop[data-drop="newmotif"]').boundingBox() // always a choice (a tree row may be its own motif)
  await page.mouse.move(from!.x + 20, from!.y + 6)
  await page.mouse.down()
  await page.mouse.move(drop!.x + drop!.width / 2, drop!.y + drop!.height / 2, { steps: 15 })
  await expect(page.locator('.dz-menu')).toBeVisible()
  await page.keyboard.press('Escape')
  await page.mouse.up()
})

test('where it came from opens whole, and stays open for the next claim', async ({ page }) => {
  await judge(page)
  test.skip(!(await count(page, 'claims to judge')), 'no claim waiting in the copy')
  const bar = page.locator('.more-bar')
  if ((await bar.innerText()).includes('shorter')) await bar.click() // start folded
  await expect(page.locator('.cl-detail')).not.toHaveClass(/open/)
  await bar.click()
  await expect(page.locator('.cl-detail')).toHaveClass(/open/)
  await page.keyboard.press('ArrowRight') // the next claim
  await expect(page.locator('.cl-detail')).toHaveClass(/open/)
})
