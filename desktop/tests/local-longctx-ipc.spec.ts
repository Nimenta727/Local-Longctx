import { EventEmitter } from 'node:events'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { expect, it, onTestFinished, vi } from 'vitest'
import type { BrowserWindow } from 'electron'
import { installLocalLongctx } from '../src/local-longctx-ipc.ts'

const stubs = vi.hoisted(() => ({
  handlers: new Map<string, (event: unknown, payload?: unknown) => unknown>(),
  userData: '',
  pick: vi.fn(),
  spawn: vi.fn(),
}))
vi.mock('electron', () => ({
  app: { getPath: () => stubs.userData, isPackaged: false, on: vi.fn() },
  ipcMain: { handle: (channel: string, handler: (event: unknown, payload?: unknown) => unknown) =>
    stubs.handlers.set(channel, handler) },
  dialog: { showOpenDialog: stubs.pick, showMessageBox: async () => ({ response: 1 }) },
  clipboard: { writeText: vi.fn() },
  shell: { openPath: vi.fn() },
}))
vi.mock('node:child_process', async original => ({
  ...await original<typeof import('node:child_process')>(), spawn: stubs.spawn,
}))

it('waits for the spawned worker rather than accepting a matching previous gateway', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'longctx-desktop-'))
  onTestFinished(async () => {
    vi.useRealTimers()
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
    stubs.handlers.clear()
    await rm(directory, { recursive: true, force: true })
  })
  stubs.userData = directory
  vi.stubEnv('LOCAL_LONGCTX_DEV_ROOT', directory)
  vi.stubEnv('LOCAL_LONGCTX_PYTHON', 'python')
  vi.useFakeTimers({ toFake: ['setTimeout'] })
  const model = join(directory, 'model.gguf')
  const engine = join(directory, 'engine')
  await Promise.all([writeFile(model, ''), writeFile(engine, '')])
  stubs.pick.mockResolvedValueOnce({ canceled: false, filePaths: [model] })
  stubs.pick.mockResolvedValueOnce({ canceled: false, filePaths: [engine] })
  const child = Object.assign(new EventEmitter(), {
    pid: 1234, stdin: Object.assign(new EventEmitter(), { end: vi.fn() }),
  })
  stubs.spawn.mockReturnValue(child)
  const gateway = (pid: number) => new Response(JSON.stringify({
    worker_pid: pid, context: { configured_native_window: 8192, output_reserve: 1024 },
  }))
  const fetch = vi.fn().mockResolvedValueOnce(gateway(999)).mockResolvedValueOnce(gateway(1234))
  vi.stubGlobal('fetch', fetch)
  installLocalLongctx(() => ({} as BrowserWindow))
  const call = async (name: string, payload?: unknown) => stubs.handlers.get('local-longctx:' + name)!({}, payload)
  await call('pick', 'model')
  await call('pick', 'engine')
  const settings = {
    context: 8192, modelLimit: 8192, output: 1024,
    threads: 4, ratio: .8, dtype: 'auto', verified: true,
  }
  const started = await call('start', settings)
  expect(started).toMatchObject({ phase: 'starting' })
  await vi.advanceTimersByTimeAsync(0)
  expect(await call('status')).toMatchObject({ phase: 'starting' })
  expect(fetch).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(1000)
  expect(await call('status')).toMatchObject({ phase: 'ready' })
  await expect(call('save-startup', { ...settings, moeStrategy: 'ssd' })).rejects.toThrow('Invalid MoE strategy')
  await expect(call('save-startup', { ...settings, experimentalSsd: true, ssdExpertOffload: true })).rejects.toThrow('requires MoE strategy offload')
  await expect(call('save-startup', { ...settings, moeStrategy: 'offload', ssdExpertOffload: 'true' })).rejects.toThrow('Invalid SSD expert offload setting')
  await expect(call('save-startup', { ...settings, dtype: 'fp8_per_token_head', experimentalSsd: true, ssdKvCheckpoint: true })).rejects.toThrow('requires Auto KV precision')
  await expect(call('save-startup', { ...settings, experimentalSsd: true, ssdKvLimitMib: 1025 })).rejects.toThrow('Invalid integer setting')
  await expect(call('save-startup', { ...settings, ramHeadroom: 0 })).rejects.toThrow('Invalid RAM headroom')
  await call('save-startup', { ...settings, context: 4096, moeStrategy: 'offload', experimentalSsd: true,
    ssdExpertOffload: true, ssdKvCheckpoint: true, ssdExpertStagingMib: 8, ssdKvLimitMib: 512, hostWeights: 20, ramHeadroom: 3 })
  expect(await call('status')).toMatchObject({
    phase: 'ready',
    settings: { context: 4096, moeStrategy: 'offload', experimentalSsd: true, ssdExpertOffload: true,
      ssdKvCheckpoint: true, ssdExpertStagingMib: 8, ssdKvLimitMib: 512 },
    activeSettings: { context: 8192, moeStrategy: 'auto', experimentalSsd: false, ssdExpertOffload: false, ssdKvCheckpoint: false },
  })
  expect(JSON.parse(await readFile(join(directory, 'local-longctx', 'config.json'), 'utf8'))).toMatchObject({
    context: 4096, moe_strategy: 'offload', experimental_ssd: true, ssd_expert_offload: true, ssd_kv_checkpoint: true,
    ssd_expert_staging_mib: 8, ssd_kv_limit_mib: 512, host_weights_gib: 20, ram_headroom_gib: 3,
  })
  expect(await call('connection')).toMatchObject({ context: 8192 })
  expect(child.stdin.end).not.toHaveBeenCalled()
  expect(await call('stop')).toMatchObject({ phase: 'stopping' })
  expect(child.stdin.end).toHaveBeenCalledOnce()
  child.emit('exit', 1, null)
  expect(await call('status')).toMatchObject({ phase: 'error', detail: expect.stringContaining('Worker exited') })
  installLocalLongctx(() => ({} as BrowserWindow))
  expect(await call('status')).toMatchObject({ phase: 'idle', settings: { ssdExpertOffload: true, ssdKvCheckpoint: true } })
  await call('save-startup', { ...settings, experimentalSsd: false, ssdExpertOffload: true,
    ssdKvCheckpoint: true, ssdExpertStagingMib: 8, ssdKvLimitMib: 512 })
  expect(JSON.parse(await readFile(join(directory, 'local-longctx', 'config.json'), 'utf8'))).toMatchObject({
    experimental_ssd: false, ssd_expert_offload: true, ssd_kv_checkpoint: true,
    ssd_expert_staging_mib: 8, ssd_kv_limit_mib: 512,
  })
})
