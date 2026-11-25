import { expect, it } from 'vitest'
import { estimateContent } from '@deepseek-ai/dsh-token-meter/estimate'
import { localToolBudget, retainDiagnostics } from '../src/local-tool-evidence.ts'
import { retainContent, type RetainableBlock } from '../src/retention.ts'

it('keeps a middle diagnostic within budget and leaves exact output available to the spill writer', () => {
  const original = 'START\n' + 'routine output\n'.repeat(150) + 'fatal: build ERR_381\n'
    + 'routine output\n'.repeat(150) + 'DONE'
  const source = [{ type: 'text' as const, text: original }]
  const price = (block: RetainableBlock) => estimateContent([block])
  const retained = retainContent(source, 100, price)
  const diagnostic = retainDiagnostics(source, retained, 35, price)
  expect(diagnostic?.block.text).toContain('fatal: build ERR_381')
  expect(price(diagnostic!.block)).toBeLessThanOrEqual(35)
  expect(source[0]?.text).toBe(original)
  expect(retainDiagnostics(source, retained, 1, price)).toBeUndefined()
  expect(localToolBudget(8192)).toBe(1024)
  expect(localToolBudget(131072)).toBe(1536)
})
