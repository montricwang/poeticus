import { expect, test } from '@playwright/test'

const featured = {
  id: '11111111-1111-4111-8111-111111111111',
  source_order: 1,
  collection: '测试词集',
  author: '贺铸',
  cipai: '青玉案',
  yusheng_title: '横塘路',
  title: null,
  incipit: '凌波不过横塘路，但目送、芳尘去。',
  review_status: 'reviewed',
  body_segments: ['凌波不过横塘路，但目送、芳尘去。', '一川烟草，满城风絮，梅子黄时雨。'],
  prefaces: [],
  text_version: 1,
}

test('首页贺铸寓声替代词牌，阅读室仍保留原词牌', async ({ page }) => {
  await page.route(/\/api\/poems\/(?:daily|11111111-1111-4111-8111-111111111111)$/, (route) =>
    route.fulfill({ json: featured }),
  )
  await page.route(/\/api\/poems\/[a-f0-9-]+\/neighbors$/, (route) =>
    route.fulfill({ json: { previous_id: null, next_id: null } }),
  )
  await page.route(/\/api\/poems\?/, (route) =>
    route.fulfill({ json: { items: [], total: 0, limit: 20, offset: 0 } }),
  )

  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 844 })
    await page.goto('/')
    const recommendation = page.getByRole('region', { name: '推荐作品' })
    await expect(recommendation.locator('.poem-reader-heading')).toHaveText('横塘路')
    await expect(recommendation.locator('.poem-reader-secondary-heading')).toHaveCount(0)
  }

  await page.getByRole('button', { name: '读这首词' }).click()
  await expect(page.locator('.poem-reader-content .poem-reader-heading')).toHaveText('横塘路')
  await expect(page.locator('.poem-reader-content .poem-reader-secondary-heading')).toHaveText(
    '青玉案',
  )
})

test('其他作者的寓声保留原词牌；深色印章填充与边框不重复叠色', async ({ page }) => {
  await page.route(/\/api\/poems\/daily$/, (route) =>
    route.fulfill({ json: { ...featured, author: '测试作者' } }),
  )
  await page.goto('/')
  const recommendation = page.getByRole('region', { name: '推荐作品' })
  await expect(recommendation.locator('.poem-reader-heading')).toHaveText('横塘路')
  await expect(recommendation.locator('.poem-reader-secondary-heading')).toHaveText('青玉案')

  await page.evaluate(() => document.documentElement.classList.add('dark'))
  const seal = page.getByRole('button', { name: '读这首词' })
  await seal.hover()
  await expect
    .poll(() =>
      seal.evaluate((button) => {
        const style = getComputedStyle(button)
        return {
          backgroundClip: style.backgroundClip,
          backgroundColor: style.backgroundColor,
          borderColor: style.borderTopColor,
        }
      }),
    )
    .toMatchObject({ backgroundClip: 'padding-box' })

  const colors = await seal.evaluate((button) => {
    const style = getComputedStyle(button)
    return { fill: style.backgroundColor, border: style.borderTopColor }
  })
  expect(colors.fill).toBe(colors.border)
})
