import { expect, test } from '@playwright/test'

test('首页可以正常渲染并提供外观设置', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveTitle('Poeticus')
  await expect(page.locator('#root')).not.toBeEmpty()
  await expect(page.getByRole('button', { name: '外观设置' })).toBeVisible()
})

test('可以切换到深色主题', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: '外观设置' }).click()
  await page.getByRole('radio', { name: '深色' }).click()
  await expect(page.locator('html')).toHaveClass(/dark/)
  await expect(page).toHaveTitle('Poeticus')
})
