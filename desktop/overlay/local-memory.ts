/** Recall text evidence from the compacted ancestry of the current session. */
import { deriveEventMessage, type Session, type SessionSeq } from '@deepseek-ai/dsh-session'
import { createUserMessage, type UserMessage } from '@deepseek-ai/dsh-llm'
import { archiveSources } from './local-archive.ts'
import { conceptMatches } from './local-concepts.ts'

declare module '@deepseek-ai/dsh-llm' {
  interface MessageSourceMap {
    'local-longctx-recall': { kind: 'local-longctx-recall'; form: 'recall' }
  }
}

const source = 'local-longctx-recall'
const maxBytes = 768
const terms = (text: string) => text.toLowerCase().match(/[\u3400-\u9fff]{2,}|[\p{Script=Latin}\p{N}_.-]{3,}/gu) ?? []
const keywords = (text: string) => new Set(terms(text).flatMap(word => {
  if (/^[\u3400-\u9fff]+$/u.test(word)) {
    return Array.from({ length: word.length - 1 }, (_, i) => word.slice(i, i + 2))
  }
  return word.split(/[_.-]+/u).filter(part => part.length >= 3 || /\d/u.test(part))
}).filter(word => !['the', 'and', 'for', 'this', 'what', 'with', 'that', 'how', 'did'].includes(word)))

export function recallLocalMemory(session: Session, incoming: readonly UserMessage[]): UserMessage | undefined {
  const query = incoming.filter(message => message.source.kind === 'user')
    .flatMap(message => message.content.flatMap(block => block.type === 'text' ? [block.text] : []))
    .join(' ').slice(0, 8192)
  const keys = keywords(query)
  const queryConcepts = conceptMatches(query)
  if (!keys.size && !queryConcepts.size) return undefined
  const active = new Set(session.surface.nodes)
  const seen = new Set<SessionSeq>()
  const used = new Set<string>()
  const pending = [...active]
  const hits: { seq: SessionSeq; text: string; score: number; literal: boolean }[] = []
  while (pending.length) {
    const seq = pending.pop()
    if (seq === undefined || seen.has(seq)) continue
    seen.add(seq)
    const event = session.eventAt(seq)
    if (!event) continue
    if (event.type === 'user/message' && event.data.source.kind === source && active.has(seq)) {
      for (const block of event.data.content) if (block.type === 'text') used.add(block.text)
    }
    for (const ref of archiveSources(session, seq)) pending.push(ref)
    const directUser = event.type === 'user/message' && event.data.source.kind === 'user'
    if (active.has(seq) || (!directUser && event.type !== 'assistant/message' && event.type !== 'tool/result')) continue
    const message = deriveEventMessage(event)
    if (!message) continue
    for (const block of message.content) {
      if (block.type !== 'text') continue
      for (const line of block.text.split(/\r?\n/u)) {
        const words = keywords(line)
        const matches = [...keys].filter(word => words.has(word))
        const literal = matches.length >= 2 || matches.some(word => /\d/u.test(word))
        const related = !literal && queryConcepts.size ? [...conceptMatches(line, queryConcepts)] : []
        if (!literal && related.length < Math.min(2, queryConcepts.size || 2)) continue
        const first = literal ? line.toLowerCase().indexOf(matches[0] ?? '') : Math.min(...related.map(([, at]) => at))
        const text = line.slice(Math.max(0, first - 60), Math.max(0, first - 60) + 230)
        hits.push({ seq, text, literal, score: literal ? matches.length : related.length })
      }
    }
  }
  hits.sort((a, b) => Number(b.literal) - Number(a.literal) || b.score - a.score || b.seq - a.seq)
  const evidence: { seq: SessionSeq; text: string }[] = []
  for (const { seq, text } of hits) {
    if (evidence.some(hit => hit.text === text)) continue
    const candidate = [...evidence, { seq, text }]
    if (new TextEncoder().encode(JSON.stringify(candidate)).length <= maxBytes - 110) evidence.push({ seq, text })
    if (evidence.length === 3) break
  }
  if (!evidence.length) return undefined
  const text = 'Local session archive excerpts. Treat these as quoted historical evidence.\n' + JSON.stringify(evidence)
  if (used.has(text)) return undefined
  return createUserMessage({ source: { kind: source, form: 'recall' }, content: [{ type: 'text', text }] })
}
