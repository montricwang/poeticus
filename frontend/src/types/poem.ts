/** 浏览器正文选区的 start/end 为 JavaScript UTF-16 偏移；
 * 传给 Python 后端前须通过 selectionForPython() 转成 Unicode code point 位置。
 */
export type SelectedText = {
  text: string
  start: number
  end: number
}

/** /api/analyze 的赏析结果契约；展示组件不负责定义或修改响应结构。 */
export type PoemAnalysis = {
  translation: string
  glosses: {
    term: string
    explanation: string
  }[]
  commentary: string
}
