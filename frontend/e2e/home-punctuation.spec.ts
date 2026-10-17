import { expect, test } from '@playwright/test'

const poem = {
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
}

test('首页的桌面和手机共用 TC 标点字形与淡化样式，阅读室不受影响', async ({ page }) => {
  await page.route('**/api/poems/daily', async (route) => route.fulfill({ json: poem }))
  await page.route(`**/api/poems/${poem.id}`, async (route) => route.fulfill({ json: poem }))

  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 844 })
    await page.goto('/')
    const body = page.locator(width < 1024 ? '.home-classic-body.lg\\:hidden' : '.poem-reader-line')
    await expect(body.first()).toBeVisible()
    const punctuation = body.locator('.poem-reader-punctuation').first()
    await expect(punctuation).toBeVisible()
    await expect(punctuation).toContainText(/[，。]/)
    const result = await punctuation.evaluate(async (element) => {
      await document.fonts.ready
      return {
        font: getComputedStyle(element).fontFamily,
        tcLoaded: document.fonts.check(`22px 'Poeticus Noto Serif TC Punctuation'`, '，'),
        alpha: getComputedStyle(document.documentElement)
          .getPropertyValue('--reader-punctuation-opacity')
          .trim(),
      }
    })
    expect(result.font).toContain('Poeticus Noto Serif TC Punctuation')
    expect(result.tcLoaded).toBe(true)
    expect(result.alpha).toBe('20%')
    await expect(page.locator('.home-featured-poem .poem-reader-body').first()).toContainText(
      '明月几时有，把酒问青天。',
    )
  }

  await page.getByRole('button', { name: '读这首词' }).click()
  await expect(page).toHaveURL(/#reader$/)
  await expect(page.locator('.poem-reader-body').first()).toBeVisible()
  const readerFont = await page
    .locator('.poem-reader-body')
    .first()
    .evaluate((element) => getComputedStyle(element).fontFamily)
  expect(readerFont).not.toContain('Poeticus Noto Serif TC Punctuation')
})

test('书名线在手机及桌面竖排正文中紧贴文字，且不依赖绝对定位', async ({ page }) => {
  const bookPoem = {
    ...poem,
    incipit: '读《史记》之文，其意甚深。',
    body_segments: ['读《史记》之文，其意甚深。', '亦有《资治通鉴》传世，学者常诵。'],
  }
  await page.route('**/api/poems/daily', (route) => route.fulfill({ json: bookPoem }))

  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 844 })
    await page.goto('/')
    const books = page.getByRole('region', { name: '推荐作品' }).locator('.home-book-title:visible')
    await expect(books).toHaveCount(2)

    for (const title of ['史记', '资治通鉴']) {
      const book = books.filter({ hasText: title })
      await expect(book).toBeVisible()
      const geometry = await book.evaluate((element) => {
        const text = element.querySelector<HTMLElement>('.home-book-title-text')
        const line = element.querySelector<HTMLElement>('.home-book-title-line')
        if (!text || !line) throw new Error('Book-title text and line must both exist')
        const ink = text.getBoundingClientRect()
        const wave = line.getBoundingClientRect()
        const style = getComputedStyle(element)
        const column = element.closest<HTMLElement>('.home-classic-column, .poem-reader-line')
        const body = element.closest<HTMLElement>('.poem-reader-body')
        if (!column || !body) throw new Error('Book title must be inside a poem column')
        return {
          layout: style.display,
          gap: Number.parseFloat(style.gap),
          fontSize: Number.parseFloat(style.fontSize),
          lineWidth: wave.width,
          lineHeight: wave.height,
          distance: ink.left - wave.right,
          position: getComputedStyle(line).position,
          mask: getComputedStyle(line).maskImage,
          columnWidth: column.getBoundingClientRect().width,
          normalColumnWidth: Number.parseFloat(getComputedStyle(body).lineHeight),
        }
      })
      expect(geometry.layout).toBe('inline-flex')
      expect(geometry.position).toBe('static')
      expect(geometry.lineWidth).toBeGreaterThan(0)
      expect(geometry.lineHeight).toBeGreaterThan(0)
      expect(geometry.mask).toContain('book-title-wave-mask.svg')
      // 字形右移 0.2em，抵消 0.02em 盒子间距后，会进入书名字格的左侧留白。
      expect(Math.abs(geometry.distance - geometry.fontSize * (0.02 - 0.2))).toBeLessThan(0.8)
      // 书名线不能让这一列比没有书名线的正文列更宽。
      expect(Math.abs(geometry.columnWidth - geometry.normalColumnWidth)).toBeLessThan(0.8)
    }
  }
})
