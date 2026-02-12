/**
 * 导出 Markdown 为带样式的 HTML 文件
 * 使用与前端预览相同的样式
 */

import { unified } from 'unified'
import remarkParse from 'remark-parse'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import remarkRehype from 'remark-rehype'
import rehypeKatex from 'rehype-katex'
import rehypeStringify from 'rehype-stringify'

// GitHub Markdown CSS (内联到 HTML 中)
const GITHUB_MARKDOWN_CSS = `
.markdown-body {
  -ms-text-size-adjust: 100%;
  -webkit-text-size-adjust: 100%;
  margin: 0;
  color: #1f2328;
  background-color: #ffffff;
  font-family: -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans",Helvetica,Arial,sans-serif,"Apple Color Emoji","Segoe UI Emoji";
  font-size: 16px;
  line-height: 1.5;
  word-wrap: break-word;
  padding: 32px;
  max-width: 900px;
  margin: 0 auto;
}

.markdown-body h1 {
  color: #10b981;
  padding-bottom: .3em;
  font-size: 2em;
  border-bottom: 1px solid #d1d9e0;
  margin-top: 24px;
  margin-bottom: 16px;
  font-weight: 700;
  line-height: 1.25;
}

.markdown-body h2 {
  color: #10b981;
  padding-bottom: .3em;
  font-size: 1.5em;
  border-bottom: 1px solid #d1d9e0;
  margin-top: 24px;
  margin-bottom: 16px;
  font-weight: 700;
  line-height: 1.25;
}

.markdown-body h3 {
  color: #10b981;
  font-size: 1.25em;
  margin-top: 24px;
  margin-bottom: 16px;
  font-weight: 700;
  line-height: 1.25;
}

.markdown-body h4 {
  color: #10b981;
  font-size: 1em;
  margin-top: 24px;
  margin-bottom: 16px;
  font-weight: 700;
  line-height: 1.25;
}

.markdown-body p {
  margin-top: 0;
  margin-bottom: 16px;
  line-height: 1.75;
}

.markdown-body a {
  color: #059669;
  text-decoration: none;
}

.markdown-body a:hover {
  text-decoration: underline;
}

.markdown-body strong {
  color: #10b981;
  font-weight: 700;
}

.markdown-body ul, .markdown-body ol {
  margin-top: 0;
  margin-bottom: 16px;
  padding-left: 2em;
}

.markdown-body li {
  margin-top: 4px;
}

.markdown-body li + li {
  margin-top: 4px;
}

.markdown-body blockquote {
  margin: 16px 0;
  padding: 0 1em;
  color: #636c76;
  border-left: 4px solid #10b98140;
  font-style: italic;
}

.markdown-body code {
  padding: .2em .4em;
  margin: 0;
  font-size: 85%;
  white-space: break-spaces;
  background-color: #f6f8fa;
  border-radius: 6px;
  font-family: ui-monospace,SFMono-Regular,SF Mono,Menlo,Consolas,Liberation Mono,monospace;
}

.markdown-body pre {
  padding: 16px;
  overflow: auto;
  font-size: 85%;
  line-height: 1.45;
  color: #e6edf3;
  background-color: #161b22;
  border-radius: 6px;
  margin-bottom: 16px;
}

.markdown-body pre code {
  padding: 0;
  margin: 0;
  font-size: 100%;
  word-break: normal;
  white-space: pre;
  background: transparent;
  border: 0;
  color: inherit;
}

.markdown-body table {
  border-spacing: 0;
  border-collapse: collapse;
  margin-top: 0;
  margin-bottom: 16px;
  width: 100%;
  overflow: auto;
}

.markdown-body table th {
  font-weight: 700;
  padding: 6px 13px;
  border: 1px solid #d1d9e0;
  background-color: #f6f8fa;
}

.markdown-body table td {
  padding: 6px 13px;
  border: 1px solid #d1d9e0;
}

.markdown-body table tr:nth-child(2n) {
  background-color: #f6f8fa;
}

.markdown-body hr {
  height: .25em;
  padding: 0;
  margin: 24px 0;
  background-color: #d1d9e0;
  border: 0;
}

.markdown-body img {
  max-width: 100%;
  box-sizing: content-box;
  border-radius: 8px;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
}

/* 目录样式 */
.markdown-body .toc {
  background-color: #f6f8fa;
  border: 1px solid #d1d9e0;
  border-radius: 6px;
  padding: 16px;
  margin-bottom: 24px;
}

.markdown-body .toc ul {
  list-style-type: none;
  padding-left: 1em;
}

.markdown-body .toc > ul {
  padding-left: 0;
}

/* 打印优化 */
@media print {
  .markdown-body {
    max-width: none;
    padding: 0;
  }
  
  .markdown-body pre {
    white-space: pre-wrap;
  }
  
  .markdown-body img {
    max-height: 400px;
    object-fit: contain;
  }
}
`

// KaTeX CSS CDN (使用 CDN 链接保持最新)
const KATEX_CSS_CDN = 'https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.min.css'

/**
 * 将 Markdown 转换为 HTML 字符串
 */
async function markdownToHtml(markdown: string): Promise<string> {
  const result = await unified()
    .use(remarkParse)
    .use(remarkGfm)
    .use(remarkMath)
    .use(remarkRehype, { allowDangerousHtml: true })
    .use(rehypeKatex)
    .use(rehypeStringify, { allowDangerousHtml: true })
    .process(markdown)

  return String(result)
}

/**
 * 生成完整的 HTML 文档
 */
function generateHtmlDocument(title: string, bodyHtml: string, baseUrl?: string): string {
  // 处理图片路径
  let processedHtml = bodyHtml
  if (baseUrl) {
    // 将相对路径的图片转换为绝对路径
    processedHtml = bodyHtml.replace(
      /src="(\/[^"]+)"/g,
      `src="${baseUrl}$1"`
    )
  }

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${escapeHtml(title)}</title>
  <link rel="stylesheet" href="${KATEX_CSS_CDN}">
  <style>
    * {
      box-sizing: border-box;
    }
    body {
      margin: 0;
      padding: 0;
      background-color: #f5f5f5;
    }
    ${GITHUB_MARKDOWN_CSS}
  </style>
</head>
<body>
  <article class="markdown-body">
    ${processedHtml}
  </article>
</body>
</html>`
}

/**
 * HTML 转义
 */
function escapeHtml(text: string): string {
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML
}

/**
 * 导出 Markdown 为 HTML 文件
 */
export async function exportToHtml(markdown: string, title: string, baseUrl?: string): Promise<void> {
  try {
    // 转换 Markdown 为 HTML
    const bodyHtml = await markdownToHtml(markdown)
    
    // 生成完整 HTML 文档
    const fullHtml = generateHtmlDocument(title, bodyHtml, baseUrl)
    
    // 创建并下载文件
    const blob = new Blob([fullHtml], { type: 'text/html;charset=utf-8' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `${title}.html`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(link.href)
  } catch (error) {
    console.error('导出 HTML 失败:', error)
    throw error
  }
}

export default exportToHtml
