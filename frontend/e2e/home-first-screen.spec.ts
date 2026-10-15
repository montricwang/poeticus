import { expect, test } from '@playwright/test'

const works = [
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
    const url = new URL(route.request().url)
    const parts = url.pathname.split('/').filter(Boolean)
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

test('first screen keeps the featured vertical poem inside 390, 1024, and 1440px', async ({
  page,
}) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '在诗词中寻一处相逢' })).toBeVisible()
  await expect(page.locator('.home-featured-poem')).not.toBeEmpty()
  for (const width of [390, 1024, 1440]) {
    await page.setViewportSize({ width, height: 844 })
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true)
    expect(
      await page
        .locator('.home-featured-poem')
        .evaluate((element) => getComputedStyle(element).writingMode),
    ).toBe('vertical-rl')
  }
  await page.getByRole('button', { name: '阅读室' }).click()
  await expect(page).toHaveURL(/#reader$/)
  await expect(page.locator('.poem-reader')).toBeVisible()
  await page.getByRole('button', { name: 'Poeticus' }).click()
  await expect(page.getByRole('heading', { name: '在诗词中寻一处相逢' })).toBeVisible()
  await page.goBack()
  await expect(page.locator('.poem-reader')).toBeVisible()
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
