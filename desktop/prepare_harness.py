"""Materialize pinned upstream source and apply only reviewed, fail-closed overlay edits.

Development checkout only. No upstream build or installer is executed here.
"""
import argparse
import json
import shutil
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
LOCK=json.loads((ROOT/"harness.lock.json").read_text(encoding="utf-8"))
CARD="packages/client/ui-settings-models/src/client/"
COMPACTION="packages/compaction/compaction-basic/"
def replace_one(text,old,new,label):
    if text.count(old)!=1:
        raise RuntimeError("upstream anchor changed: "+label)
    return text.replace(old,new,1)

def modify(root,path,edits):
    file=root/path
    text=file.read_text(encoding="utf-8")
    for old,new in edits:
        text=replace_one(text,old,new,path)
    file.write_text(text,encoding="utf-8")

def apply(root):
    for name,dest in (("LocalLongctxPanel.tsx",CARD),("LocalCachePanel.tsx",CARD),("local-longctx-ipc.ts","apps/desktop/src/"),("local-memory.ts",COMPACTION+"src/"),
                      ("local-archive.ts",COMPACTION+"src/"),("local-task-state.ts",COMPACTION+"src/"),
                      ("local-tool-evidence.ts","packages/spill/spill-policy/src/")):
        target=root/dest/name
        if target.exists():
            raise RuntimeError("overlay destination already exists")
        shutil.copyfile(ROOT/"overlay"/name,target)
    concepts=json.loads((ROOT.parent/"longctx"/"recall_concepts.json").read_text(encoding="utf-8"))
    concepts_file=root/COMPACTION/"src/local-concepts.ts"
    with concepts_file.open("x",encoding="utf-8") as fp:
        fp.write("const aliases = " + json.dumps(concepts,ensure_ascii=False) + """\n
const patterns = Object.entries(aliases).map(([name, values]) => [name, new RegExp(values.join('|'), 'iu')] as const)
export function conceptMatches(text: string, requested?: ReadonlyMap<string, number>): Map<string, number> {
  const result = new Map<string, number>()
  for (const [name, pattern] of patterns) {
    if (requested !== undefined && !requested.has(name)) continue
    const match = pattern.exec(text)
    if (match) result.set(name, match.index)
  }
  return result
}
""")
    modify(root,COMPACTION+"src/region.ts",[
        ("import { frameSummary } from './summarizer.ts'",
         "import { frameSummary } from './summarizer.ts'\nimport { localTaskState } from './local-task-state.ts'"),
        ("""  const checkpointMessage = createUserMessage({
    content: frameSummary(summaryResult.summary),
    source: compactCheckpointSource(compactionId, sourceCommandId),
  })""", """  const source = compactCheckpointSource(compactionId, sourceCommandId)
  let checkpointMessage = createUserMessage({ content: frameSummary(summaryResult.summary), source })
  if (summaryResult.provider === 'local-longctx' && summaryResult.model === 'local-longctx') {
    const evidence = localTaskState(agent.session, prepared.shadowedSeqs)
    if (evidence !== undefined) {
      const summary = [...summaryResult.summary, evidence]
      const enriched = createUserMessage({ content: frameSummary(summary), source })
      if (dependencies.meter.estimateMessage(enriched) < prepared.shadowedRouteTokenCount) {
        summaryResult = { ...summaryResult, summary }
        checkpointMessage = enriched
      }
    }
  }""")])
    shutil.copyfile(ROOT/"tests"/"local-longctx-ipc.spec.ts",
                    root/"apps/desktop/tests/local-longctx-ipc.spec.ts")
    shutil.copyfile(ROOT/"tests"/"local-memory.spec.ts",
                    root/"packages/compaction/compaction-basic/tests/local-memory.spec.ts")
    shutil.copyfile(ROOT/"tests"/"local-tool-evidence.spec.ts",
                    root/"packages/spill/spill-policy/tests/local-tool-evidence.spec.ts")
    modify(root,"packages/core/agent/src/runtime-types.ts",[
        ("LlmAttemptId, LlmCallConfig, LlmFailure, MessageId, ReasoningEffortId, ResolvedRetryPolicy, StreamChunk,",
         "LlmAttemptId, LlmCallConfig, LlmFailure, Message, MessageId, ReasoningEffortId, ResolvedRetryPolicy, StreamChunk, ToolSchema,"),
        ("signal: AbortSignal; modelSelection: Readonly<ModelSelection> }, next: () => Promise<PreStepDecision>",
         "signal: AbortSignal; modelSelection: Readonly<ModelSelection>; promptPreview?: { tools: readonly ToolSchema[]; system: readonly Message[] } }, next: () => Promise<PreStepDecision>")])
    modify(root,"packages/core/agent-loop/src/agent.ts",[
        ("'agent/pre-step', { messages: claimed, ...position, signal, modelSelection: selection },",
         """'agent/pre-step', {
          messages: claimed, ...position, signal, modelSelection: selection,
          ...selection.provider === 'local-longctx' && selection.model === 'local-longctx' ? {
            promptPreview: { tools: assembly.tools, system: assembly.systemUpdates(false).map(update => update.message) },
          } : {},
        },""")])
    modify(root,"packages/spill/spill-policy/src/index.ts",[
        ("import { retainContent } from './retention.ts'", "import { retainContent } from './retention.ts'\nimport { localToolBudget, retainDiagnostics } from './local-tool-evidence.ts'"),
        ("  const maxTokens = cap", """  const defaultMaxTokens = cap
  const localRoute = (exec: ToolExecution) => {
    const route = exec.agent?.session.requestHeader?.()?.config ?? exec.agent?.options
    return route?.provider === 'local-longctx' && route.model === 'local-longctx'
  }"""),
        ("    if (!retainable(content)) return undefined", """    if (!retainable(content)) return undefined
    const local = localRoute(exec)
    const textOnly = content.every(block => block.type === 'text')
    const localCap = local && textOnly ? localToolBudget(exec.agent?.session.requestContext?.()?.contextWindow) : undefined
    const maxTokens = localCap === undefined ? defaultMaxTokens : Math.min(localCap, defaultMaxTokens)"""),
        ("""      const retained = retainContent(content, Math.max(0, maxTokens - reserved), price)
      const footer = notice(retained.omittedBytes, retained.omittedImages)""", """      const available = Math.max(0, maxTokens - reserved)
      const diagnosticBudget = local && textOnly ? Math.floor(available / 4) : 0
      let retained = retainContent(content, available - diagnosticBudget, price)
      const diagnostics = retainDiagnostics(content, retained, diagnosticBudget, price)
      if (diagnostics === undefined && diagnosticBudget > 0) retained = retainContent(content, available, price)
      const footer = notice(retained.omittedBytes - (diagnostics?.sourceBytes ?? 0), retained.omittedImages)"""),
        ("[...retained.head, GAP, ...retained.tail, {",
         "[...retained.head, GAP, ...retained.tail, ...(diagnostics ? [diagnostics.block] : []), {")])
    modify(root,"packages/spill/spill-policy/tests/spill-policy.spec.ts",[
        ("describe('disabled mode', () => {", """it('spills local tool output early, preserves the full body and retains a middle error', async () => {
  const { ctx, spill } = await setup({ maxInlineTokens: 12500 })
  const body = 'START\\n' + 'ordinary build progress\\n'.repeat(300)
    + 'fatal: compiler returned ERR_381\\n' + 'ordinary build progress\\n'.repeat(300) + 'DONE'
  ctx.tools.register(textTool('build-log', body))
  const request = exec('build-log')
  request.agent!.session.requestHeader = () => ({ config: { provider: 'local-longctx', model: 'local-longctx' } })
  request.agent!.session.requestContext = () => ({ provider: 'local-longctx', model: 'local-longctx', contextWindow: 8192 })
  const result = await executeToolFixture(ctx, request)
  expect(spill?.saves[0]?.content).toBe(body)
  expect(textOf(result.content)).toContain('fatal: compiler returned ERR_381')
  expect(textOf(result.content)).toContain('Full formatted result stored at: /spill/build-log.txt')
  expect(estimateContent(result.content)).toBeLessThanOrEqual(1024)
  expect(result.isError).toBe(false)
})

describe('disabled mode', () => {""")])
    modify(root,CARD+"ModelsSection.tsx",[
        ("import { useId, useState } from 'react'","import { useId, useState } from 'react'\nimport { LocalLongctxPanel } from './LocalLongctxPanel.tsx'"),
        ("return (\n    <div className={styles['section']}>","return (\n    <div className={styles['section']}>\n      <LocalLongctxPanel />")])
    modify(root,CARD+"CustomProviderCard.tsx",[
        ("import { useEffect, useState } from 'react'","import { useEffect, useState } from 'react'\nimport { localLongctxBridge } from './LocalLongctxPanel.tsx'"),
        ("  return (\n    <div className={styles['editor']}>","""  const local = localLongctxBridge()
  const useLocal = async (): Promise<void> => {
    if (!local || profileDisabled || listBusy || taken.includes('local-longctx')) return
    if (!protocols.includes('anthropic-messages')) { setFailure('Anthropic Messages protocol unavailable'); return }
    setBusy(true)
    try {
      const c = await local.connection()
      setRoute('local-longctx')
      setDisplayName('Local-Longctx')
      setBaseURL(c.baseURL)
      setProtocol('anthropic-messages')
      setKeyDraft(c.key)
      setModels([{id:c.model,name:'Local-Longctx',contextWindow:c.context,maxTokens:c.output,input:['text']}])
      setFailure(undefined)
    } catch (e) { setFailure(String(e)) }
    finally { setBusy(false) }
  }
  return (
    <div className={styles['editor']}>
      {local ? <button type="button" disabled={profileDisabled || listBusy || taken.includes('local-longctx')} onClick={()=>{void useLocal()}}>Local-Longctx 本地模型预设 / Local model preset</button> : null}""")])
    modify(root,"packages/compaction/compaction-basic/src/index.ts",[
        ("import { Context, Service } from '@deepseek-ai/cordis'","import { Context, Service } from '@deepseek-ai/cordis'\nimport { recallLocalMemory } from './local-memory.ts'"),
        ("      { agent, signal },\n      next,","      { agent, signal, modelSelection, promptPreview, step },\n      next,"),
        ("      if (!signal.aborted) {\n        try {\n          const result = await this.compactIfNeeded",
         """      const local = modelSelection.provider === 'local-longctx' && modelSelection.model === 'local-longctx'
      if (!local && !signal.aborted) {
        try {
          const result = await this.compactIfNeeded"""),
        ("      return next()\n    })\n\n    ctx.on('agent/status'", """      const decision = await next()
      if (decision.kind === 'reject' || signal.aborted || !local) return decision
      try {
        const info = await this.ctx.llm.resolveModelInfo(modelSelection.provider, modelSelection.model, signal)
        const window = info.context?.contextWindow
        if (window === undefined) return decision
        const previous = agent.session.requestHeader()
        const sameRoute = previous?.config.provider === modelSelection.provider && previous.config.model === modelSelection.model
        const header: EpochHeader = {
          config: sameRoute ? previous.config : { ...modelSelection, ...agent.options.maxTokens === undefined ? {} : { maxTokens: agent.options.maxTokens } },
          ...sameRoute && previous.adapterDefaults !== undefined ? { adapterDefaults: previous.adapterDefaults } : {},
          ...promptPreview === undefined
            ? (sameRoute && previous.tools !== undefined ? { tools: previous.tools } : {})
            : (promptPreview.tools.length > 0 ? { tools: [...promptPreview.tools] } : {}),
        }
        const meter = this.ctx.tokenMeter
        const pending = [...decision.messages, ...(promptPreview?.system ?? [])]
          .reduce((sum, message) => sum + meter.estimateMessage(message), 0)
        const reserve = reservedCompletionTokens(header, info.defaultMaxTokens)
        const spec = resolveCompactSpec(resolveTargetPolicy(this.config, header.config), window, reserve)
        if (sameRoute && meter.measure(agent.session, header).totalTokens + pending >= spec.thresholdTokens) {
          const result = await this.compactPressure(agent, header, signal, false, pending)
          if (result !== null) logResult(result, 'step pressure')
        }
        if (step !== 1) return decision
        const headroom = spec.thresholdTokens - meter.measure(agent.session, header).totalTokens - pending
        if (headroom <= 0) return decision
        const recalled = recallLocalMemory(agent.session, decision.messages)
        if (recalled === undefined || meter.estimateMessage(recalled) >= headroom) return decision
        return { ...decision, messages: [...decision.messages, recalled] }
      } catch (error: unknown) {
        signal.throwIfAborted()
        const message = error instanceof Error ? error.message : String(error)
        ctx.logger.warn(`local step budget could not be estimated: ${message}`)
        return decision
      }
    })

    ctx.on('agent/status'"""),
        ("        const range = selectCompactableRange(agent.session, measurement, 0)",
         """        const retain = header.config.provider === 'local-longctx'
          ? Math.ceil(measurement.totalTokens * 0.22) : 0
        const range = selectCompactableRange(agent.session, measurement, retain)"""),
        ("    const config = target === undefined\n      ? this.config","""    const routed = routedTarget(agent.session)
    const local = [routed, target].find(route => route?.provider === 'local-longctx' && route.model === 'local-longctx')
    if (local !== undefined) {
      const info = await this.ctx.llm.resolveModelInfo(local.provider, local.model, signal)
      const header = agent.session.requestHeader()
      const reserve = header === undefined ? (info.defaultMaxTokens ?? 0) : reservedCompletionTokens(header, info.defaultMaxTokens)
      const maxTokens = Math.max(1, Math.min(640, reserve || 640))
      const summary = await summarizeWithLlm(this.ctx, {
        summarizationProvider: local.provider, summarizationModel: local.model, maxTokens,
      }, input, agent, local, signal)
      return summary
    }
    const config = target === undefined
      ? this.config"""),
        ("    const policy = resolveTargetPolicy(this.config, target)\n    const meter", """    const policy = resolveTargetPolicy(this.config, target)
    // The first step after switching routes prices the committed local request.
    if (target.provider === 'local-longctx' && requireBelowThreshold
      && routedTarget(agent.session)?.provider !== 'local-longctx') return null
    const meter""")])
    modify(root,"packages/compaction/compaction-basic/src/index.ts",[
        ("    requireBelowThreshold: boolean,\n", "    requireBelowThreshold: boolean,\n    pendingTokens = 0,\n"),
        ("    if (measurement.totalTokens < spec.thresholdTokens) return null\n\n    // Once pressure qualifies",
         "    if (measurement.totalTokens + pendingTokens < spec.thresholdTokens) return null\n\n    // Once pressure qualifies"),
        ("    if (measurement.totalTokens < spec.thresholdTokens) return null\n\n    let result:",
         "    if (measurement.totalTokens + pendingTokens < spec.thresholdTokens) return null\n\n    let result:"),
        ("if (measurement.totalTokens < spec.thresholdTokens) return result",
         "if (measurement.totalTokens + pendingTokens < spec.thresholdTokens) return result")])
    modify(root,"packages/compaction/compaction-basic/tests/compaction-basic.spec.ts",[
        ("describe('automatic listener and loader composition', () => {", """it('counts newly admitted local content and tools before choosing pressure compaction', async () => {
  const modelSelection = { provider: 'local-longctx', model: 'local-longctx' }
  const ctx = createContext(2400)
  ctx.llm.registerAdapter([modelSelection.provider], new ContextAdapter(2400))
  onTestFinished(() => ctx.fiber.dispose())
  const compact = service({ auto: true }, ctx)
  const session = conversation(6, 'fixture '.repeat(45))
  const config = { ...modelSelection, maxTokens: 128 }
  session.append('request/header', { header: { config }, reason: 'change' })
  const threshold = resolveCompactSpec(resolveTargetPolicy(compact.config, config), 2400, 128).thresholdTokens
  const tools = [{ name: 'echo', description: 'tool schema '.repeat(150), inputSchema: {} }]
  const messages = [createUserMessage({
    source: { kind: 'user' }, content: [{ type: 'text', text: 'new question '.repeat(225) }],
  })]
  const current = ctx.tokenMeter.measure(session, { config, tools }).totalTokens
  expect(ctx.tokenMeter.measure(session).totalTokens).toBeLessThan(threshold)
  expect(current + ctx.tokenMeter.estimateMessage(messages[0]!)).toBeGreaterThan(threshold)
  const decision = await agentEvents(ctx, agent(session, 'local-longctx')).waterfall('agent/pre-step', {
    modelSelection, messages, turn: 7, step: 1, signal: SIGNAL,
    promptPreview: { tools, system: [] },
  }, () => Promise.resolve({ kind: 'enter' as const, messages }))
  expect(compact.calls.length).toBeGreaterThan(0)
  expect(decision).toMatchObject({ kind: 'enter', messages })
})

describe('automatic listener and loader composition', () => {""")])
    modify(root,COMPACTION+"tests/compaction-basic.spec.ts",[
        ("describe('pressure measurement and retention', () => {", """it('persists verifiable local task state in the committed checkpoint', async () => {
  const model = 'local-longctx'
  const session = conversation(4, 'Constraint: preserve public API.\\n'
    + 'Rejected migration because compatibility checks failed.\\n'
    + 'Decision: keep the existing route.\\nTODO: verify the windows build.\\n'
    + 'routine details '.repeat(60))
  const compact = service()
  compact.summaryProvider = model
  compact.summaryModel = model
  const [start, end] = session.surface.nodes
  const result = await compact.compactRegion(start!, end!, agent(session, model), SIGNAL)
  const block = result.summary.find(item => item.type === 'text' && item.text.includes('Source excerpts'))
  expect(block?.type === 'text' && block.text).toContain('preserve public API')
  expect(block?.type === 'text' && block.text).toContain('verify the windows build')
  expect(session.eventAt(result.summarySeq)?.data).toMatchObject({ summary: result.summary })
  expect(session.deriveMessages().flatMap(message => message.content)).toContainEqual(block)
})

describe('pressure measurement and retention', () => {""")])
    modify(root,"packages/compaction/compaction-basic/src/config.ts",[
        ("policy.provider === target.provider && policy.model === target.model\n  ))",
         """policy.provider === target.provider && policy.model === target.model
  )) ?? (target.provider === 'local-longctx' && target.model === 'local-longctx' ? {
    provider: target.provider, model: target.model, thresholdRatio: 0.8,
    headroomTokens: 384, maxTokens: 640, retainRatio: 0.22, maxOverflowRetries: 1,
  } satisfies ModelCompactPolicyConfig : undefined)""")])
    modify(root,"packages/bundle/web-app/cordis.patch.yml",[
        ("- id: system-prompt\n", """- id: session-log-deepseek
  config:
    enabled: false

- id: session-telemetry-otel
  config:
    mode: DISABLED

- id: system-prompt
""")])
    modify(root,"apps/desktop/src/main.ts",[
        ("import { installFileActions } from './file-actions.ts'","import { installFileActions } from './file-actions.ts'\nimport { installLocalLongctx } from './local-longctx-ipc.ts'"),
        ("app.setAppLogsPath()", "app.setAppLogsPath(join(app.getPath('userData'), 'logs'))"),
        ("  ipcMain.handle(DESKTOP_IPC.boot, async (event) => {","  installLocalLongctx(assertProductSender)\n  ipcMain.handle(DESKTOP_IPC.boot, async (event) => {")])
    modify(root,"apps/desktop/src/preload-app.ts",[
        ("markDocumentPlatform()","""if (location.protocol === `${SCHEME}:` && location.hostname === 'app' && process.isMainFrame) {
  contextBridge.exposeInMainWorld('localLongctx', {
    status: () => ipcRenderer.invoke('local-longctx:status'),
    openData: () => ipcRenderer.invoke('local-longctx:open-data'),
    copyKey: () => ipcRenderer.invoke('local-longctx:copy-key'),
    pick: (kind: 'model' | 'engine') => ipcRenderer.invoke('local-longctx:pick', kind),
    start: (settings: unknown) => ipcRenderer.invoke('local-longctx:start', settings),
    stop: () => ipcRenderer.invoke('local-longctx:stop'),
    connection: () => ipcRenderer.invoke('local-longctx:connection'),
    cacheStatus: () => ipcRenderer.invoke('local-longctx:cache-status'),
    cacheApply: (draft: unknown) => ipcRenderer.invoke('local-longctx:cache-apply', draft),
  })
}
markDocumentPlatform()""")])
    modify(root,"apps/desktop/scripts/electron-builder-config.mjs",[
        ("productName: 'DeepSeek Harness'","productName: 'Local-Longctx Studio'"),
        ("name: 'DeepSeek Harness', schemes: ['dsh']","name: 'Local-Longctx Studio', schemes: ['dsh']")])
    # Original vector mark. Do not modify copyright, licenses, internal package identifiers,
    # or provider names. Raster icons and all other brand surfaces require a release audit.
    for name in ("icon.svg","icon-macos.svg","icon-windows.svg"):
        shutil.copyfile(ROOT/"overlay"/"studio.svg",root/"apps/desktop/resources"/name)
    (root/"LOCAL_LONGCTX_PREVIEW.txt").write_text("Independent development overlay; not a release. Preserve upstream MIT notices.\n",encoding="utf-8")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--destination",type=Path,default=ROOT/"upstream")
    a=p.parse_args()
    dest=a.destination.resolve()
    if dest.exists():
        raise SystemExit("Destination exists; choose a fresh directory. No existing source is overwritten.")
    subprocess.run(["git","clone","--no-checkout","--filter=blob:none",LOCK["url"],str(dest)],check=True)
    subprocess.run(["git","-C",str(dest),"checkout","--detach",LOCK["revision"]],check=True)
    rev=subprocess.check_output(["git","-C",str(dest),"rev-parse","HEAD"],text=True).strip()
    if rev!=LOCK["revision"]:
        raise RuntimeError("incorrect upstream revision")
    apply(dest)
    print("Prepared development source:",dest)
    print("Do not package or distribute until build, provider, telemetry, updater and branding audits pass.")

if __name__=="__main__":
    main()
