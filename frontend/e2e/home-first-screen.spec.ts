import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { HOME_INITIAL_REVEAL_MS, READER_INITIAL_REVEAL_MS } from '../src/lib/entrance-motion'

const works = [
  {
    id: 'e1fe9c90-c29b-468a-910d-973a331da960',
    source_order: 4,
    collection: '测试词集',
    author: '柳永',
    cipai: '戚氏',
    title: null,
    yusheng_title: null,
    incipit: '晚秋天。一霎微雨洒庭轩。',
    review_status: 'reviewed',
    body_segments: [
      '晚秋天。一霎微雨洒庭轩。槛菊萧疏，井梧零乱惹残烟。凄然。望乡关。',
      '孤馆度日如年。风露渐变，悄悄至更阑。',
    ],
    prefaces: [],
    text_version: 1,
  },
  {
    id: '00000000-0000-0000-0000-000000000001',
    source_order: 1,
    collection: '测试词集',
    author: '温庭筠',
    cipai: '菩萨蛮',
    title: null,
    yusheng_title: null,
    incipit: '小山重叠金明灭，鬓云欲度香腮雪。',
    review_status: 'reviewed',
    body_segments: ['小山重叠金明灭，鬓云欲度香腮雪。', '懒起画蛾眉，弄妆梳洗迟。'],
    prefaces: [],
    text_version: 1,
  },
  {
    id: '2098ddf7-55bb-4923-be66-6af4cae58d78',
    source_order: 3,
    collection: '测试词集',
    author: '辛弃疾',
    cipai: '破阵子',
    title: '为陈同甫赋壮词以寄之',
    yusheng_title: null,
    incipit: '醉里挑灯看剑，梦回吹角连营。',
    review_status: 'reviewed',
    body_segments: ['醉里挑灯看剑，梦回吹角连营。', '马作的卢飞快，弓如霹雳弦惊。'],
    prefaces: [],
    text_version: 1,
  },
  {
    id: '00000000-0000-0000-0000-000000000002',
    source_order: 2,
    collection: '测试词集',
    author: '苏轼',
    cipai: '水调歌头',
    title: null,
    yusheng_title: null,
    incipit: '明月几时有，把酒问青天。',
    review_status: 'reviewed',
    body_segments: ['明月几时有，把酒问青天。', '不知天上宫阙，今夕是何年。'],
    prefaces: [],
    text_version: 1,
  },
]

// 首页首次入场时搜索区是 inert：不能在不可交互阶段填值再误判搜索功能失败。
async function fillHomeSearch(page: Page, value: string) {
  const slot = page.locator('[data-home-search-slot]')
  await expect(slot).toBeVisible()
  await expect(slot).not.toHaveAttribute('inert', '')
  const input = page.getByRole('searchbox', { name: '搜索词人、词牌或诗句' })
  await input.fill(value)
  await expect(input).toHaveValue(value)
}

test.beforeEach(async ({ page }) => {
  // The first-screen test is independent of the local corpus/Postgres service.
  await page.route(/\/api\/poems(?:\/[^?]+)?(?:\?.*)?$/, async (route) => {
    const url = new URL(route.request().url())
    const parts = url.pathname.split('/').filter(Boolean)
    if (parts.at(-1) === 'daily') {
      // Today's recommendation is a separate API; keep the UI fixture deterministic.
      await route.fulfill({ json: works[0] })
      return
    }
    if (parts.at(-1) === 'neighbors') {
      await route.fulfill({ json: { previous_id: null, next_id: null } })
      return
    }
    if (parts.length === 3) {
      const poem = works.find((work) => work.id === parts[2])
      await route.fulfill(poem ? { json: poem } : { status: 404, json: { detail: '未找到作品' } })
      return
    }
    const q = url.searchParams.get('q')?.trim() ?? ''
    const matches = q
      ? works.filter((work) =>
          [work.author, work.cipai, work.incipit].some((field) => field?.includes(q)),
        )
      : works
    const limit = Number(url.searchParams.get('limit') ?? 20)
    const offset = Number(url.searchParams.get('offset') ?? 0)
    await route.fulfill({
      json: {
        items: matches.slice(offset, offset + limit).map((work) => ({
          id: work.id,
          source_order: work.source_order,
          collection: work.collection,
          author: work.author,
          cipai: work.cipai,
          title: work.title,
          yusheng_title: work.yusheng_title,
          incipit: work.incipit,
          review_status: work.review_status,
        })),
        total: matches.length,
        limit,
        offset,
      },
    })
  })
})

test('homepage poem stays visible across phone, tablet and desktop widths', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('button', { name: '首页词牌排版调试' })).toHaveCount(0)
  const recommendation = page.getByRole('region', { name: '推荐作品' })
  await expect(page.getByRole('heading', { name: '美要眇兮宜修' })).toBeVisible()
  await expect(recommendation.locator('.home-featured-poem')).not.toBeEmpty()
  for (const width of [320, 390, 820, 1023, 1024, 1440]) {
    await page.setViewportSize({ width, height: 844 })
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true)
    expect(
      await recommendation
        .locator('.home-featured-poem')
        .evaluate((element) => getComputedStyle(element).writingMode),
    ).toBe('vertical-rl')
    if (width < 1024) {
      // Safari 的窄屏首页不依赖 RTL 滚动容器来定位正文。
      await expect(recommendation.locator('.home-classic-body[class~="lg:hidden"]')).toBeVisible()
      await expect(recommendation.locator('header')).toBeVisible()
      expect(
        await recommendation.locator('[data-recommendation-scrollport]').evaluate((element) => ({
          direction: element.getAttribute('dir'),
          overflow: getComputedStyle(element).overflowX,
        })),
      ).toEqual({ direction: null, overflow: 'hidden' })
      // 手机采用文字视觉重心居中，印章跟随真实诗文左缘。
      const layout = await page.locator('[aria-label="推荐作品"]').evaluate((section) => {
        const poem = section.querySelector('.home-featured-poem')
        const button = section.querySelector<HTMLButtonElement>('button')
        if (!poem || !button) throw new Error('Missing recommendation content')
        const view = section.querySelector('[data-recommendation-scrollport]')
        if (!view) throw new Error('Missing recommendation viewport')
        const viewport = view.getBoundingClientRect()
        const poemRect = poem.getBoundingClientRect()
        const buttonRect = button.getBoundingClientRect()
        return {
          visualOffset: Math.abs(
            (poemRect.left + poemRect.right) / 2 - (viewport.left + viewport.right) / 2,
          ),
          sealGap: poemRect.left - buttonRect.right,
        }
      })
      expect(layout.visualOffset).toBeLessThan(60)
      expect(layout.sealGap).toBeGreaterThanOrEqual(8)
      expect(layout.sealGap).toBeLessThanOrEqual(18)
      await expect(recommendation.locator('.home-classic-body[class~="lg:hidden"]')).toContainText(
        '晚秋天',
      )
    } else {
      // 桌面仅保留按句断列的排版。
      await expect(recommendation.locator('.poem-reader-line').first()).toBeVisible()
      await expect(recommendation.locator('.home-classic-body[class~="lg:hidden"]')).toHaveCount(0)
    }
    await expect(page.getByRole('group', { name: '推荐作品排版方式' })).toHaveCount(0)
  }
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(recommendation.locator('.home-classic-body[class~="lg:hidden"]')).toBeVisible()

  await page.getByRole('button', { name: '阅读室' }).click()
  await expect(page).toHaveURL(/#reader$/)
  await expect(page.locator('.poem-reader')).toBeVisible()
  await page.getByRole('button', { name: 'Poeticus' }).click()
  await expect(page.getByRole('heading', { name: '美要眇兮宜修' })).toBeVisible()
  await page.goBack()
  await expect(page.locator('.poem-reader')).toBeVisible()
})

test('homepage entrance replays after reader navigation and search appears last', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  const search = page.locator('[data-home-search-slot]')
  await expect(page.locator('.home-recommendation-initial')).toHaveCount(1)
  await expect(search).toHaveCSS('opacity', '0')
  await expect(search).toHaveAttribute('inert', '')
  const column = page.locator('.home-recommendation-initial .home-classic-column').first()
  await expect(column).toHaveCSS('animation-duration', '0.24s')
  await expect(page.locator('.home-divider-initial')).toHaveCSS('animation-delay', '0.47s')
  const homeTiming = await page.evaluate(() => {
    const columns = [
      ...document.querySelectorAll<HTMLElement>(
        '.home-recommendation-initial .home-classic-column',
      ),
    ]
    const divider = document.querySelector<HTMLElement>('.home-divider-initial')
    if (!columns.length || !divider) throw new Error('Missing initial entrance columns or divider')
    const secondsToMs = (time: string) => Number.parseFloat(time) * 1000
    const lastColumnEnd = Math.max(
      ...columns.map((column) => {
        const css = getComputedStyle(column)
        return secondsToMs(css.animationDelay) + secondsToMs(css.animationDuration)
      }),
    )
    const line = getComputedStyle(divider)
    const dividerStart = secondsToMs(line.animationDelay)
    return {
      lastColumnEnd,
      dividerStart,
      dividerEnd: dividerStart + secondsToMs(line.animationDuration),
    }
  })
  expect(homeTiming.lastColumnEnd).toBeLessThan(homeTiming.dividerStart)
  expect(homeTiming.dividerEnd).toBeLessThan(HOME_INITIAL_REVEAL_MS)
  await expect(page.locator('.home-recommendation-initial')).toHaveCount(0, { timeout: 3000 })
  await expect(search).toHaveClass(/home-search-intro-revealing/)
  const title = search.locator('.home-search-intro-title')
  const form = search.locator('.home-search-intro-form')
  const underline = search.locator('.home-search-intro-divider')
  await expect(title).toHaveCSS('animation-name', 'home-search-float-up')
  await expect(title).toHaveCSS('animation-duration', '0.19s')
  await expect(form).toHaveCSS('animation-name', 'home-search-float-up')
  await expect(form).toHaveCSS('animation-delay', '0.06s')
  await expect(underline).toHaveCSS('animation-delay', '0.06s')
  const searchFinishAfterReveal = await form.evaluate((element) => {
    const css = getComputedStyle(element)
    return 1000 * (Number.parseFloat(css.animationDuration) + Number.parseFloat(css.animationDelay))
  })
  expect(HOME_INITIAL_REVEAL_MS + searchFinishAfterReveal).toBeLessThan(1000)
  const floatUp = await title.evaluate((element) => {
    const animation = element
      .getAnimations()
      .find((item) => item instanceof CSSAnimation && item.animationName === 'home-search-float-up')
    const keyframes =
      animation?.effect instanceof KeyframeEffect ? animation.effect.getKeyframes() : undefined
    return keyframes?.map((frame) => ({
      opacity: String(frame.opacity),
      transform: String(frame.transform),
    }))
  })
  expect(floatUp).toEqual([
    { opacity: '0', transform: 'translateY(14px)' },
    { opacity: '1', transform: 'translateY(0px)' },
  ])
  await expect(search).toHaveCSS('opacity', '1')
  await expect(search).not.toHaveAttribute('inert', '')

  await page.getByRole('button', { name: '阅读室' }).click()
  await page.getByRole('button', { name: 'Poeticus' }).click()
  await expect(page.locator('.home-recommendation-initial')).toHaveCount(1)
  await expect(search).toHaveCSS('opacity', '0')
  await expect(search).toHaveAttribute('inert', '')
  await expect(page.locator('.home-recommendation-initial')).toHaveCount(0, { timeout: 3000 })
  await expect(search).toHaveClass(/home-search-intro-revealing/)
  await expect(search.locator('.home-search-intro-title')).toHaveCSS(
    'animation-name',
    'home-search-float-up',
  )
  await expect(search.locator('.home-search-intro-form')).toHaveCSS('animation-delay', '0.06s')
  await expect(search).toHaveCSS('opacity', '1')

  // A viewport resize changes layout, not the home route, so the intro stays finished.
  await page.setViewportSize({ width: 402, height: 874 })
  await expect(page.locator('.home-recommendation-initial')).toHaveCount(0)
  await expect(search).not.toHaveAttribute('inert', '')
})

test('desktop poem columns finish before the divider and sub-second search phase', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/')
  await expect(page.locator('.home-recommendation-initial')).toHaveCount(1)
  const desktopColumns = page.locator('.home-recommendation-initial .poem-reader-line')
  await expect(desktopColumns.first()).toHaveCSS('animation-duration', '0.17s')
  const timeline = await page.evaluate(() => {
    const lines = [
      ...document.querySelectorAll<HTMLElement>('.home-recommendation-initial .poem-reader-line'),
    ]
    const divider = document.querySelector<HTMLElement>('.home-divider-initial')
    if (!lines.length || !divider) throw new Error('Missing desktop entrance lines or divider')
    const secondsToMs = (time: string) => Number.parseFloat(time) * 1000
    const lastLineEnd = Math.max(
      ...lines.map((line) => {
        const css = getComputedStyle(line)
        return secondsToMs(css.animationDelay) + secondsToMs(css.animationDuration)
      }),
    )
    const dividerCss = getComputedStyle(divider)
    const dividerStart = secondsToMs(dividerCss.animationDelay)
    return {
      lastLineEnd,
      dividerStart,
      dividerEnd: dividerStart + secondsToMs(dividerCss.animationDuration),
    }
  })
  expect(timeline.lastLineEnd).toBeLessThan(timeline.dividerStart)
  expect(timeline.dividerEnd).toBeLessThan(HOME_INITIAL_REVEAL_MS)
  await expect(page.locator('.home-recommendation-initial')).toHaveCount(0, { timeout: 3000 })
  const search = page.locator('[data-home-search-slot]')
  await expect(search).not.toHaveAttribute('inert', '')
  await expect(search.locator('.home-search-intro-form')).toHaveCSS('animation-duration', '0.195s')
})

test('Poeticus navigation from a direct reader visit replays the home introduction', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await page.goto('/#reader')
  await page.getByRole('button', { name: 'Poeticus' }).click()
  const search = page.locator('[data-home-search-slot]')
  await expect(page.locator('.home-recommendation-initial')).toHaveCount(1)
  await expect(search).toHaveCSS('opacity', '0')
  await expect(search).toHaveAttribute('inert', '')
  await expect(page.locator('.home-recommendation-initial')).toHaveCount(0, { timeout: 3000 })
  await expect(search).toHaveCSS('opacity', '1')
  await expect(search).not.toHaveAttribute('inert', '')
})

test('reader first entrance reveals lines once and leaves ordinary poem switching unchanged', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await page.goto('/')
  await fillHomeSearch(page, '苏轼')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  const results = page.getByRole('region', { name: '搜索结果' })
  await expect(results).toContainText('水调歌头')
  await results.getByRole('button', { name: /水调歌头/ }).click()
  await expect(page.locator('.reader-intro-revealing')).toHaveCount(1, { timeout: 4500 })
  await expect(page.locator('.reader-intro-revealing .poem-reader-line').first()).toHaveCSS(
    'animation-name',
    'home-column-rise',
  )
  const readerLastLineEnd = await page
    .locator('.reader-intro-revealing .poem-reader-line')
    .evaluateAll((lines) =>
      Math.max(
        ...lines.map((line) => {
          const css = getComputedStyle(line)
          return (
            1000 *
            (Number.parseFloat(css.animationDelay) + Number.parseFloat(css.animationDuration))
          )
        }),
      ),
    )
  expect(readerLastLineEnd).toBeLessThan(READER_INITIAL_REVEAL_MS)
  expect(READER_INITIAL_REVEAL_MS).toBeLessThan(1000)
  await expect(page.locator('.reader-intro-revealing')).toHaveCount(0, { timeout: 4000 })
  await expect(page.getByRole('heading', { name: '水调歌头' })).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.locator('.reader-intro-revealing')).toHaveCount(0)
})

test('submitted home search replaces recommendation and clearing restores it', async ({ page }) => {
  await page.goto('/')
  const recommendation = page.getByRole('region', { name: '推荐作品' })
  const searchbox = page.getByRole('searchbox', { name: '搜索词人、词牌或诗句' })
  const results = page.getByRole('region', { name: '搜索结果' })
  await expect(recommendation).toBeVisible()
  await expect(results).toHaveCount(0)
  await expect(searchbox).toHaveAttribute('autocomplete', 'off')
  await expect(searchbox).toHaveAttribute('type', 'text')
  await expect(searchbox).toHaveAttribute('inputmode', 'search')
  await expect(searchbox).toHaveAttribute('enterkeyhint', 'search')

  await fillHomeSearch(page, '苏轼')
  // 原生搜索框的 X 不再出现，保留本站自己的一个清空按钮。
  await expect(page.getByRole('button', { name: '清空输入' })).toHaveCount(1)
  // 只有正式提交才进入结果模式；输入和焦点变化均不隐藏推荐。
  await expect(recommendation).toBeVisible()
  await expect(results).toHaveCount(0)
  await page.getByRole('button', { name: '搜索', exact: true }).click()

  await expect(recommendation).toHaveCount(0)
  await expect(results).toBeVisible()
  await expect(results).toContainText('水调歌头')
  await expect(results).toContainText('找到 1 首作品')
  await expect(searchbox).not.toBeFocused()
  await expect
    .poll(() =>
      page
        .getByRole('region', { name: '馆藏搜索' })
        .evaluate((section) => section.getBoundingClientRect().top),
    )
    .toBeLessThan(180)
  expect(await page.locator('#home').evaluate((main) => main.scrollTop)).toBe(0)

  await results.getByRole('button', { name: '清除搜索' }).click()
  await expect(results).toHaveCount(0)
  await expect(recommendation).toBeVisible()
  await expect(searchbox).toHaveValue('')
  await expect(page.getByRole('heading', { name: '美要眇兮宜修' })).toBeVisible()
})

test('home search field moves between positions instead of hiding the whole page', async ({
  page,
}) => {
  await page.goto('/')
  const search = page.getByRole('region', { name: '馆藏搜索' })
  const initialTop = await search.evaluate((element) => element.getBoundingClientRect().top)
  await fillHomeSearch(page, '苏轼')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await expect(page.getByRole('region', { name: '搜索结果' })).toBeVisible()
  // FLIP 维持同一个搜索元素，只改变它的屏幕位置，不整页淡出。
  await expect(page.locator('#home > div')).toHaveCSS('opacity', '1')
  await expect
    .poll(() => search.evaluate((element) => element.getBoundingClientRect().top))
    .toBeLessThan(initialTop - 100)
  await page.getByRole('button', { name: '清除搜索' }).click()
  await expect(page.getByRole('region', { name: '推荐作品' })).toBeVisible()
  await expect
    .poll(() => search.evaluate((element) => element.getBoundingClientRect().top))
    .toBeGreaterThan(initialTop - 5)
})

test('delayed FLIP search never flashes at its destination', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await page.goto('/')
  const section = page.getByRole('region', { name: '馆藏搜索' })
  const origin = await section.evaluate((element) => element.getBoundingClientRect().top)
  await fillHomeSearch(page, '苏轼')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  const samples = await section.evaluate((element) => {
    const animation = element.getAnimations()[0]
    if (!animation) throw new Error('Missing FLIP animation')
    animation.pause()
    const positions: number[] = []
    for (const time of [0, 20, 59, 60]) {
      animation.currentTime = time
      positions.push(element.getBoundingClientRect().top)
    }
    animation.play()
    return { fill: animation.effect?.getTiming().fill, positions }
  })
  expect(samples.fill).toBe('backwards')
  expect(samples.positions.every((top) => Math.abs(top - origin) < 2)).toBe(true)
})

test('poem float-up does not create a temporary vertical scrollbar', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/')
  await fillHomeSearch(page, '苏轼')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await page
    .getByRole('region', { name: '搜索结果' })
    .getByRole('button', { name: '清除搜索' })
    .click()
  await expect(page.locator('.home-recommendation-revealing')).toBeVisible()
  const dimensions = await page.locator('[data-recommendation-scrollport]').evaluate((element) => ({
    overflowX: getComputedStyle(element).overflowX,
    overflowY: getComputedStyle(element).overflowY,
    delta: element.scrollHeight - element.clientHeight,
  }))
  expect(dimensions.overflowX).toBe('auto')
  expect(dimensions.overflowY).toBe('hidden')
  // The 6px translateY can enlarge scrollHeight; it must not activate a scrollbar.
  expect(dimensions.delta).toBeGreaterThanOrEqual(0)
})

test('delayed FLIP keeps search at its original position before moving', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await page.goto('/')
  await fillHomeSearch(page, '苏轼')
  const frames = await page.evaluate(async () => {
    const form = document.querySelector<HTMLFormElement>('form[role="search"]')
    const search = document.querySelector<HTMLElement>('[aria-label="馆藏搜索"]')
    if (!form || !search) throw new Error('Missing search form')
    const originalTop = search.getBoundingClientRect().top
    form.requestSubmit()
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
    const animation = search.getAnimations().find((item) => item.effect?.getTiming().delay === 60)
    if (!animation) throw new Error('Missing delayed search FLIP animation')
    animation.pause()
    const points = [0, 30, 59, 60, 160, 660].map((time) => {
      animation.currentTime = time
      return search.getBoundingClientRect().top
    })
    animation.finish()
    return { originalTop, points, fill: animation.effect?.getTiming().fill }
  })
  expect(frames.fill).toBe('backwards')
  for (const point of frames.points.slice(0, 4)) {
    expect(Math.abs(point - frames.originalTop)).toBeLessThan(2)
  }
  expect(frames.points.at(-1)).toBeLessThan(frames.originalTop - 80)
})

test('staggering poem lines never enables a transient vertical scrollbar', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/')
  await fillHomeSearch(page, '苏轼')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  const results = page.getByRole('region', { name: '搜索结果' })
  await expect(results).toContainText('水调歌头')
  await results.getByRole('button', { name: '清除搜索' }).click()
  const samples = await page.evaluate(async () => {
    const port = document.querySelector<HTMLElement>('[data-recommendation-scrollport]')
    if (!port) throw new Error('Missing featured poem scrollport')
    const values: { overflowX: string; overflowY: string; overflowPx: number }[] = []
    for (let frame = 0; frame < 55; frame++) {
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
      values.push({
        overflowX: getComputedStyle(port).overflowX,
        overflowY: getComputedStyle(port).overflowY,
        overflowPx: port.scrollHeight - port.clientHeight,
      })
    }
    return values
  })
  expect(samples.length).toBeGreaterThan(40)
  expect(samples.every((sample) => sample.overflowY === 'hidden')).toBe(true)
  expect(samples.every((sample) => sample.overflowX === 'auto')).toBe(true)
})

test('moving search overlaps the recommendation fade', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await page.goto('/')
  await fillHomeSearch(page, '苏轼')
  const observations = await page.evaluate(async () => {
    document.querySelector<HTMLFormElement>('form[role="search"]')?.requestSubmit()
    const frames: { opacity: number; line: number; moving: boolean }[] = []
    for (let frame = 0; frame < 28; frame++) {
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
      const poem = document.querySelector<HTMLElement>('.home-recommendation-exiting')
      const line = document.querySelector<HTMLElement>('.home-divider-exiting')
      const search = document.querySelector<HTMLElement>('[aria-label="馆藏搜索"]')
      frames.push({
        opacity: poem ? Number(getComputedStyle(poem).opacity) : 0,
        line: line ? Number(getComputedStyle(line).opacity) : 0,
        moving: !!search?.getAnimations().some((animation) => animation.playState === 'running'),
      })
    }
    return frames
  })
  expect(
    observations.some(({ opacity, moving }) => moving && opacity > 0.05 && opacity < 0.95),
  ).toBe(true)
  expect(observations.some(({ line, moving }) => moving && line < 0.25)).toBe(true)
  await expect(page.locator('.home-recommendation-exiting')).toHaveCount(0)
  await expect(page.getByRole('region', { name: '搜索结果' })).toContainText('水调歌头')
})

test('returning recommendation never overlaps the moving search field', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await page.goto('/')
  await fillHomeSearch(page, '苏轼')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  const results = page.getByRole('region', { name: '搜索结果' })
  await expect(results).toContainText('水调歌头')
  await results.getByRole('button', { name: '清除搜索' }).click()

  // 验证实际动画的每一帧；不能只断言动画结束后的布局没有重叠。
  const overlap = await page.evaluate(async () => {
    const search = document.querySelector<HTMLElement>('[aria-label="馆藏搜索"]')
    const poem = document.querySelector<HTMLElement>('[aria-label="推荐作品"]')
    const recommendation = document.querySelector<HTMLElement>('[data-home-recommendation-slot]')
    if (!search || !poem || !recommendation) throw new Error('Missing homepage sections')
    const moveDuration = search.getAnimations()[0]?.effect?.getTiming().duration
    const samples: { searchY: number; poemBottom: number; opacity: number }[] = []
    const started = performance.now()
    while (performance.now() - started < 900) {
      const searchBox = search.getBoundingClientRect()
      const poemBox = poem.getBoundingClientRect()
      const opacity = Number(getComputedStyle(recommendation).opacity)
      if (searchBox.top < poemBox.bottom && searchBox.bottom > poemBox.top && opacity > 0.02) {
        samples.push({ searchY: searchBox.top, poemBottom: poemBox.bottom, opacity })
      }
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
    }
    return { samples, moveDuration, finalOpacity: getComputedStyle(recommendation).opacity }
  })
  expect(overlap.moveDuration).toBe(600)
  expect(overlap.samples).toEqual([])
  expect(overlap.finalOpacity).toBe('1')
})

test('returning columns stagger before the divider grows from its center', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await page.goto('/')
  await fillHomeSearch(page, '苏轼')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  const results = page.getByRole('region', { name: '搜索结果' })
  await expect(results).toContainText('水调歌头')
  await results.getByRole('button', { name: '清除搜索' }).click()
  await expect(page.locator('.home-recommendation-revealing')).toBeVisible()
  const sequence = await page.evaluate(() => {
    const divider = document.querySelector<HTMLElement>('.home-divider-growing')
    const columns = [
      ...document.querySelectorAll<HTMLElement>(
        '.home-recommendation-revealing .home-classic-column, .home-recommendation-revealing .poem-reader-line',
      ),
    ]
    if (!divider || columns.length < 2) throw new Error('Missing staggered text or divider')
    return {
      dividerAnimation: getComputedStyle(divider).animationName,
      dividerDelay: parseFloat(getComputedStyle(divider).animationDelay) * 1000,
      columns: columns.map((column) => ({
        name: getComputedStyle(column).animationName,
        delay: parseFloat(getComputedStyle(column).animationDelay) * 1000,
      })),
    }
  })
  expect(sequence.dividerAnimation).toContain('home-line-reveal')
  expect(sequence.columns.every((column) => column.name.includes('home-column-rise'))).toBe(true)
  expect(sequence.columns.at(-1)?.delay).toBeGreaterThan(sequence.columns[0].delay)
  expect(sequence.dividerDelay).toBeGreaterThan(sequence.columns.at(-1)?.delay ?? 0)
  await expect(page.locator('.home-recommendation-divider')).toHaveCSS('opacity', '1', {
    timeout: 3000,
  })
})

test('revealed recommendation does not replay after viewport resize', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await fillHomeSearch(page, '苏轼')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await page
    .getByRole('region', { name: '搜索结果' })
    .getByRole('button', { name: '清除搜索' })
    .click()
  await expect(page.locator('.home-recommendation-revealing')).toHaveCount(0, { timeout: 3000 })
  await page.setViewportSize({ width: 402, height: 874 })
  await expect(page.locator('.home-recommendation-revealing')).toHaveCount(0)
  const count = await page
    .locator('.home-classic-column')
    .evaluateAll(
      (columns) =>
        columns.filter((column) =>
          column.getAnimations().some((animation) => animation.playState === 'running'),
        ).length,
    )
  expect(count).toBe(0)
})

test('home search results reuse catalog title typography for full-width middle dots', async ({
  page,
}) => {
  await page.goto('/')
  await fillHomeSearch(page, '辛弃疾')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  const title = page.getByRole('region', { name: '搜索结果' }).locator('.poeticus-catalog-title')
  await expect(title).toHaveText('破阵子·为陈同甫赋壮词以寄之')
  await expect(title).toHaveCSS('font-family', /Noto Sans SC Variable/)

  await title.evaluate(() => document.fonts.ready)
  const middleDotWidthRatio = await title.evaluate((element) => {
    const style = getComputedStyle(element)
    const context = document.createElement('canvas').getContext('2d')
    if (!context) throw new Error('Missing canvas context')
    context.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`
    return context.measureText('·').width / context.measureText('中').width
  })
  expect(middleDotWidthRatio).toBeCloseTo(1, 1)
})

test('mobile catalog title preserves full-width middle dots', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/#reader')
  await page.getByRole('button', { name: '展开作品目录' }).click()
  const title = page
    .locator('#poem-catalog .poeticus-catalog-title')
    .filter({ hasText: '破阵子·为陈同甫赋壮词以寄之' })
  await expect(title).toBeVisible()
  await expect(title).toHaveCSS('font-family', /Noto Sans SC Variable/)
})

test('font readiness can stall without hiding mobile home and reader forever', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  // 模拟 iOS 字体下载长时间未完成，旧实现会永远停留在 opacity: 0。
  await page.addInitScript(() => {
    Object.defineProperty(document.fonts, 'ready', {
      configurable: true,
      get: () => new Promise<FontFaceSet>(() => {}),
    })
  })
  await page.goto('/')

  const recommendation = page.getByRole('region', { name: '推荐作品' })
  const searchSlot = page.locator('[data-home-search-slot]')
  await expect(recommendation).toContainText('晚秋天')
  await expect(recommendation).toHaveCSS('opacity', '1', { timeout: 4000 })
  await expect(searchSlot).toHaveCSS('opacity', '1', { timeout: 4000 })
  await expect(searchSlot).not.toHaveAttribute('inert', '')

  await page.getByRole('button', { name: '阅读室' }).click()
  const reader = page.getByRole('region', { name: '诗词阅读' }).locator('.poem-reader')
  await expect(reader).toContainText('晚秋天')
  await expect(reader).toHaveCSS('opacity', '1', { timeout: 4000 })

  await page.getByRole('button', { name: 'Poeticus' }).click()
  await expect(recommendation).toHaveCSS('opacity', '1', { timeout: 4000 })
  await expect(searchSlot).toHaveCSS('opacity', '1', { timeout: 4000 })
  await expect(searchSlot).not.toHaveAttribute('inert', '')
})

test('direct mobile reader entry does not wait indefinitely for fonts', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await page.addInitScript(() => {
    Object.defineProperty(document.fonts, 'ready', {
      configurable: true,
      get: () => new Promise<FontFaceSet>(() => {}),
    })
  })
  await page.goto('/#reader')
  const reader = page.getByRole('region', { name: '诗词阅读' }).locator('.poem-reader')
  await expect(reader).toContainText('晚秋天')
  await expect(reader).toHaveCSS('opacity', '1', { timeout: 4000 })
})

test('first entries are immediate for reduced-motion users', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  await expect(page.getByRole('region', { name: '推荐作品' })).toBeVisible()
  await expect(page.locator('.home-recommendation-initial')).toHaveCount(0)
  await expect(page.locator('[data-home-search-slot]')).toHaveCSS('opacity', '1')
  await expect(page.locator('[data-home-search-slot]')).not.toHaveAttribute('inert', '')
  await page.getByRole('button', { name: '阅读室' }).click()
  await expect(page.locator('.reader-intro-waiting, .reader-intro-revealing')).toHaveCount(0)
  await page.getByRole('button', { name: 'Poeticus' }).click()
  await expect(page.locator('.home-recommendation-initial')).toHaveCount(0)
  await expect(page.locator('[data-home-search-slot]')).toHaveCSS('opacity', '1')
})

test('home search view transition remains immediate with reduced motion', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  await fillHomeSearch(page, '苏轼')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await expect(page.getByRole('region', { name: '推荐作品' })).toHaveCount(0)
  await expect(page.getByRole('region', { name: '搜索结果' })).toContainText('水调歌头')
  await expect(page.locator('#home > div')).toHaveCSS('opacity', '1')
})

test('search a poet and enter the existing reader', async ({ page }) => {
  await page.goto('/')
  await fillHomeSearch(page, '苏轼')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  const results = page.getByRole('region', { name: '搜索结果' })
  await expect(results).toContainText('水调歌头')
  await expect(results).toContainText('找到 1 首作品')
  await results.getByRole('button', { name: /水调歌头/ }).click()
  await expect(page).toHaveURL(/#reader$/)
  await expect(page.getByRole('heading', { name: '水调歌头' })).toBeVisible()
})
