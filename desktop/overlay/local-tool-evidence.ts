/** Keep verifiable diagnostic lines from the omitted middle of a local tool result. */
import type { RetainableBlock, RetainedContent } from './retention.ts'

const DIAGNOSTIC = /\b(?:error|fatal|panic|traceback|exception|failed|failure|ERR_[A-Z0-9_]+)\b|错误|失败/iu
const HEADING = '\n\n[Selected diagnostic lines]\n'

export function localToolBudget(window: number | undefined): number {
  return window === undefined ? 768 : Math.max(384, Math.min(1536, Math.floor(window / 8)))
}

export function retainDiagnostics(
  source: readonly RetainableBlock[], ends: RetainedContent, budget: number,
  price: (block: RetainableBlock) => number,
): { block: Extract<RetainableBlock, { type: 'text' }>; sourceBytes: number } | undefined {
  if (!budget || source.some(block => block.type !== 'text')) return undefined
  const text = (blocks: readonly RetainableBlock[]) => blocks.map(block => block.type === 'text' ? block.text : '').join('')
  const original = text(source)
  const start = text(ends.head).length
  const end = original.length - text(ends.tail).length
  // Discard partial boundary lines so an excerpt always matches the full stored line.
  const first = start === 0 || original[start - 1] === '\n' ? start : original.indexOf('\n', start) + 1
  const last = end === original.length || original[end - 1] === '\n' ? end : original.lastIndexOf('\n', end - 1) + 1
  if (first < start || first >= last) return undefined
  const lines: string[] = []
  for (const line of original.slice(first, last).split('\n')) {
    if (line.length > 400 || !DIAGNOSTIC.test(line) || lines.includes(line)) continue
    const candidate = { type: 'text' as const, text: HEADING + [...lines, line].join('\n') }
    if (price(candidate) <= budget) lines.push(line)
    if (lines.length === 3) break
  }
  if (!lines.length) return undefined
  return { block: { type: 'text', text: HEADING + lines.join('\n') },
    sourceBytes: lines.reduce((bytes, line) => bytes + Buffer.byteLength(line, 'utf8'), 0) }
}
