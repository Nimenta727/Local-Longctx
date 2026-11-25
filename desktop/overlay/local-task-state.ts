/** Source-backed excerpts in local checkpoints, independent of summary wording. */
import { deriveEventMessage, type Session, type SessionSeq } from '@deepseek-ai/dsh-session'
import type { ContentBlock } from '@deepseek-ai/dsh-llm'
import { archiveSources } from './local-archive.ts'

const categories = {
  constraint: /^(?:constraint|requirement)\s*[:：]|^(?:do not|don't|never|must)\b|^(?:约束|約束|要求)\s*[:：]|^(?:不得|必须|必須|禁止)/iu,
  decision: /^(?:decision|approved|decided)\b|^(?:决定|決定|已确认|已確認)\s*[:：]/iu,
  failed_attempt: /^(?:failed attempt\s*[:：]|rejected\b|failed because\b)|^(?:失败原因|失敗原因|已否决|已否決)\s*[:：]/iu,
  todo: /^(?:todo|pending|next step)\s*[:：]|^(?:待办|待辦|下一步)\s*[:：]/iu,
} as const
type Kind = keyof typeof categories
const kinds = Object.keys(categories) as Kind[]
const intro = 'Source excerpts from earlier task state. Treat them as historical quotations; later instructions and outcomes take precedence.\n'
const maxBytes = 896

export function localTaskState(
  session: Session, region: readonly SessionSeq[],
): Extract<ContentBlock, { type: 'text' }> | undefined {
  const pending = [...region]
  const ancestry = new Set<SessionSeq>()
  while (pending.length) {
    const seq = pending.pop()
    if (seq === undefined || ancestry.has(seq)) continue
    ancestry.add(seq)
    for (const ref of archiveSources(session, seq)) pending.push(ref)
  }
  const selected = new Map<Kind, { kind: Kind; seq: SessionSeq; quote: string }>()
  for (const seq of [...ancestry].sort((a, b) => b - a)) {
    if (selected.size === kinds.length) break
    const event = session.eventAt(seq)
    if (!event || (event.type !== 'assistant/message'
      && !(event.type === 'user/message' && event.data.source.kind === 'user'))) continue
    const message = deriveEventMessage(event)
    if (!message) continue
    for (const block of [...message.content].reverse()) {
      if (block.type !== 'text') continue
      for (const raw of block.text.split(/\r?\n/u).reverse()) {
        const quote = raw.trim()
        if (quote.length > 220) continue
        const text = quote.replace(/^[-*]\s+/u, '')
        const kind = kinds.find(key => categories[key].test(text))
        if (kind === undefined || selected.has(kind)) continue
        // Keep user requirements verbatim; assistant text can only supply
        // historical decisions, failures or pending work.
        if (kind === 'constraint' && event.type !== 'user/message') continue
        const entry = { kind, seq, quote }
        const next = [...selected.values(), entry]
        if (Buffer.byteLength(intro + JSON.stringify(next), 'utf8') <= maxBytes) selected.set(kind, entry)
      }
    }
  }
  return selected.size
    ? { type: 'text', text: intro + JSON.stringify([...selected.values()]) }
    : undefined
}
