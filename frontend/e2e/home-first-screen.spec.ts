import { expect, test } from '@playwright/test'

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

  await searchbox.fill('苏轼')
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
  await page.getByRole('searchbox', { name: '搜索词人、词牌或诗句' }).fill('苏轼')
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

test('returning recommendation never overlaps the moving search field', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await page.goto('/')
  await page.getByRole('searchbox', { name: '搜索词人、词牌或诗句' }).fill('苏轼')
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

test('home search results reuse catalog title typography for full-width middle dots', async ({
  page,
}) => {
  await page.goto('/')
  await page.getByRole('searchbox', { name: '搜索词人、词牌或诗句' }).fill('辛弃疾')
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

test('home search view transition remains immediate with reduced motion', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  await page.getByRole('searchbox', { name: '搜索词人、词牌或诗句' }).fill('苏轼')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await expect(page.getByRole('region', { name: '推荐作品' })).toHaveCount(0)
  await expect(page.getByRole('region', { name: '搜索结果' })).toContainText('水调歌头')
  await expect(page.locator('#home > div')).toHaveCSS('opacity', '1')
})

test('search a poet and enter the existing reader', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('searchbox', { name: '搜索词人、词牌或诗句' }).fill('苏轼')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  const results = page.getByRole('region', { name: '搜索结果' })
  await expect(results).toContainText('水调歌头')
  await expect(results).toContainText('找到 1 首作品')
  await results.getByRole('button', { name: /水调歌头/ }).click()
  await expect(page).toHaveURL(/#reader$/)
  await expect(page.getByRole('heading', { name: '水调歌头' })).toBeVisible()
})
