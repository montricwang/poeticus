import { expect, test } from '@playwright/test'

const poem = {
  id: '00000000-0000-0000-0000-000000000022',
  source_order: 22,
  collection: '测试词集',
  author: '辛弃疾',
  cipai: '喜迁莺',
  title: null,
  yusheng_title: null,
  incipit: '暑风凉月，爱亭亭无数。',
  review_status: 'reviewed',
  body_segments: [
    '暑风凉月，爱亭亭无数，绿衣持节。掩冉如羞，参差似妒，拥出芙渠花发。',
    '步衬潘娘堪恨，貌比六郎谁洁？添白鹭，晚晴时公子，佳人并列。',
  ],
  prefaces: [],
  text_version: 1,
}

test.beforeEach(async ({ page }) => {
  await page.route('**/api/poems/daily', async (route) => route.fulfill({ json: poem }))
  await page.route(/\/api\/poems\?.*$/, async (route) => {
    await route.fulfill({
      json: {
        items: [{ ...poem, body_segments: undefined }],
        total: 1,
        limit: 20,
        offset: 0,
      },
    })
  })
})

test('搜索结果不改变同一视口下的推荐词断列', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  const poemBody = page.locator('.home-classic-body.lg\\:hidden')
  await expect(poemBody.locator('.home-classic-column').first()).toBeVisible()
  const before = await page.evaluate(() => ({
    budget: getComputedStyle(document.querySelector('#home')!).getPropertyValue(
      '--home-classic-max-height',
    ),
    columns: [
      ...document.querySelectorAll('.home-classic-body.lg\\:hidden .home-classic-column'),
    ].map((element) => element.textContent),
  }))
  await page.getByRole('searchbox', { name: '搜索词人、词牌或诗句' }).fill('暑风凉月')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await expect(page.getByRole('region', { name: '搜索结果' })).toBeVisible()
  await expect
    .poll(async () =>
      page.evaluate(() => ({
        budget: getComputedStyle(document.querySelector('#home')!).getPropertyValue(
          '--home-classic-max-height',
        ),
        columns: [
          ...document.querySelectorAll('.home-classic-body.lg\\:hidden .home-classic-column'),
        ].map((element) => element.textContent),
      })),
    )
    .toEqual(before)
})

test('窄矮视口显示明确节选，可纵向滚动且没有页面横向溢出', async ({ page }) => {
  for (const { width, height } of [
    { width: 317, height: 446 },
    { width: 744, height: 490 },
    { width: 864, height: 606 },
  ]) {
    await page.setViewportSize({ width, height })
    await page.goto('/')
    const body = page.locator('.home-classic-body.lg\\:hidden')
    await expect(body.locator('.home-classic-column').first()).toBeVisible()
    await expect(page.locator('.home-featured-poem header')).toBeVisible()
    const shape = await page.evaluate(() => {
      const main = document.querySelector<HTMLElement>('#home')!
      const article = document.querySelector<HTMLElement>('.home-featured-poem')!
      const scrollport = document.querySelector<HTMLElement>('[data-recommendation-scrollport]')!
      return {
        pageOverflow: document.documentElement.scrollWidth > innerWidth,
        bodyBudget: parseFloat(
          getComputedStyle(main).getPropertyValue('--home-classic-max-height'),
        ),
        verticalScroll: main.scrollHeight > main.clientHeight,
        articleFits: article.getBoundingClientRect().width <= scrollport.clientWidth,
      }
    })
    expect(shape.pageOverflow).toBe(false)
    expect(shape.bodyBudget).toBeGreaterThanOrEqual(288)
    expect(shape.verticalScroll).toBe(true)
    expect(shape.articleFits).toBe(true)
  }
})
