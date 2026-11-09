import * as React from 'react'

/**
 * 制度正文的轻量渲染：只处理我们模板里真实用到的语法
 * （# / ## / ###、表格、列表、引用块、加粗、行内代码）。
 * 不引第三方 md 库，也不用 dangerouslySetInnerHTML——制度正文是可信内容，
 * 但审批系统里不引入 HTML 注入面更稳妥。
 */

/** 行内：**加粗** 与 `代码` */
function Inline({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean)
  return (
    <>
      {parts.map((p, i) => {
        if (p.startsWith('**') && p.endsWith('**')) {
          return (
            <strong key={i} className="font-semibold text-ink">
              {p.slice(2, -2)}
            </strong>
          )
        }
        if (p.startsWith('`') && p.endsWith('`')) {
          return (
            <code key={i} className="rounded bg-[#F3F4F6] px-1 py-0.5 text-[12px] text-[#B91C1C]">
              {p.slice(1, -1)}
            </code>
          )
        }
        return <React.Fragment key={i}>{p}</React.Fragment>
      })}
    </>
  )
}

/** 一张 markdown 表格 */
function Table({ rows }: { rows: string[][] }) {
  const [head, ...body] = rows
  return (
    <div className="my-3 overflow-x-auto rounded-lg border border-line">
      <table className="w-full text-left text-[12.5px]">
        <thead>
          <tr className="bg-[#F7F8FA] text-xs text-muted">
            {head.map((c, i) => (
              <th key={i} className="whitespace-nowrap px-3 py-2 font-medium">
                <Inline text={c} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((r, i) => (
            <tr key={i} className="border-t border-line-soft">
              {r.map((c, j) => (
                <td key={j} className="px-3 py-2 align-top text-ink-2">
                  <Inline text={c} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function splitRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((c) => c.trim())
}

export function MarkdownBody({ text }: { text: string }) {
  const lines = text.split(/\r?\n/)
  const blocks: React.ReactNode[] = []
  let para: string[] = []
  let list: string[] = []
  let table: string[][] = []

  const flushPara = () => {
    if (para.length) {
      blocks.push(
        <p key={`p${blocks.length}`} className="my-2 text-[13px] leading-7 text-ink-2">
          <Inline text={para.join('')} />
        </p>,
      )
      para = []
    }
  }
  const flushList = () => {
    if (list.length) {
      blocks.push(
        <ul key={`l${blocks.length}`} className="my-2 flex flex-col gap-1 pl-1">
          {list.map((item, i) => (
            <li key={i} className="flex gap-2 text-[13px] leading-7 text-ink-2">
              <span className="mt-[9px] h-1 w-1 shrink-0 rounded-full bg-faint" />
              <span>
                <Inline text={item} />
              </span>
            </li>
          ))}
        </ul>,
      )
      list = []
    }
  }
  const flushTable = () => {
    if (table.length) {
      blocks.push(<Table key={`t${blocks.length}`} rows={table} />)
      table = []
    }
  }
  const flushAll = () => {
    flushPara()
    flushList()
    flushTable()
  }

  for (let i = 0; i < lines.length; i += 1) {
    const raw = lines[i]
    const line = raw.trimEnd()

    // 表格
    if (line.trim().startsWith('|')) {
      flushPara()
      flushList()
      // 分隔行 |---|---| 跳过
      if (/^\|[\s:|-]+\|?$/.test(line.trim()) && line.includes('-')) continue
      table.push(splitRow(line))
      continue
    }
    flushTable()

    if (!line.trim()) {
      flushAll()
      continue
    }
    if (line.startsWith('# ')) {
      flushAll()
      blocks.push(
        <h1 key={`h1${blocks.length}`} className="mb-3 text-[19px] font-bold text-ink">
          {line.slice(2)}
        </h1>,
      )
      continue
    }
    if (line.startsWith('## ')) {
      flushAll()
      blocks.push(
        <h2 key={`h2${blocks.length}`} className="mb-2 mt-6 border-l-[3px] border-primary pl-2.5 text-[15px] font-semibold text-ink">
          {line.slice(3)}
        </h2>,
      )
      continue
    }
    if (line.startsWith('### ')) {
      flushAll()
      blocks.push(
        <h3 key={`h3${blocks.length}`} className="mb-1.5 mt-4 text-[13.5px] font-semibold text-primary">
          {line.slice(4)}
        </h3>,
      )
      continue
    }
    if (line.startsWith('> ')) {
      flushAll()
      blocks.push(
        <blockquote
          key={`q${blocks.length}`}
          className="my-2 rounded-r-lg border-l-[3px] border-[#F59E0B] bg-[#FFFBEB] px-3 py-2 text-[12.5px] leading-6 text-[#92400E]"
        >
          <Inline text={line.slice(2)} />
        </blockquote>,
      )
      continue
    }
    if (/^[-*]\s+/.test(line)) {
      flushPara()
      list.push(line.replace(/^[-*]\s+/, ''))
      continue
    }
    if (/^\d+\.\s+/.test(line)) {
      flushPara()
      list.push(line.replace(/^\d+\.\s+/, ''))
      continue
    }
    if (/^-{3,}$/.test(line.trim())) {
      flushAll()
      continue
    }
    flushList()
    para.push(line.trim())
  }
  flushAll()

  return <div>{blocks}</div>
}
