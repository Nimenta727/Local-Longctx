import { describe, expect, it } from 'vitest'
import { SessionSeq, type Session } from '@deepseek-ai/dsh-session'
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import { resolveCompactSpec, resolveConfig, resolveTargetPolicy } from '../src/config.ts'
import { recallLocalMemory } from '../src/local-memory.ts'

describe('local archival recall', () => {
  it('leaves room for a checkpoint within an 8K local window', () => {
    const target = { provider: 'local-longctx', model: 'local-longctx' }
    const spec = resolveCompactSpec(resolveTargetPolicy(resolveConfig(), target), 8192, 1024)
    expect(spec.thresholdTokens).toBe(6553)
    expect(spec.retainTokens).toBeLessThan(spec.thresholdTokens)
    expect(spec.maxOverflowRetries).toBe(1)
  })


  it('reads only ancestors and preserves tool records as bounded quoted text', () => {
    const query = createUserMessage({
      source: { kind: 'user' },
      content: [{ type: 'text', text: 'What happened in decode_cache.py at ERR_381?' }],
    })
    const output = (text: string) => ({
      type: 'tool/result', surfaceOp: 'append',
      data: { message: { content: [{ type: 'text', text }] } },
    })
    const events = new Map<number, unknown>([
      [0, output('decode_cache.py: ERR_381 corrupted cache')],
      [1, output('decode_cache.py ERR_381 from an unrelated branch')],
      [2, { ...output('Output pruned'), surfaceOp: { op: 'replace', startSeq: 0, endSeq: 0 }, sourceEventSeqs: [0] }],
      [3, { type: 'compaction/summary' }],
      [4, { type: 'user/message', data: query, surfaceOp: { op: 'replace', startSeq: 2, endSeq: 2 }, sourceEventSeqs: [2, 3] }],
    ])
    const session = {
      surface: { nodes: [SessionSeq(4)] },
      eventAt: (seq: number) => events.get(seq),
    } as unknown as Session
    const recalled = recallLocalMemory(session, [query])
    const text = JSON.stringify(recalled)
    expect(text).toContain('corrupted cache')
    expect(text).not.toContain('unrelated branch')
    expect(recalled?.source.kind).toBe('local-longctx-recall')
    expect(recallLocalMemory(session, [])).toBeUndefined()
  })
})
