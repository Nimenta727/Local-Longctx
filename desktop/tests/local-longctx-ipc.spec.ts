import { EventEmitter } from 'node:events'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
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
  const started = await call('start', {
    context: 8192, modelLimit: 8192, output: 1024,
    threads: 4, ratio: .8, dtype: 'auto', verified: true,
  })
  expect(started).toMatchObject({ phase: 'starting' })
  await vi.advanceTimersByTimeAsync(0)
  expect(await call('status')).toMatchObject({ phase: 'starting' })
  expect(fetch).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(1000)
  expect(await call('status')).toMatchObject({ phase: 'ready' })
  expect(await call('stop')).toMatchObject({ phase: 'stopping' })
  expect(child.stdin.end).toHaveBeenCalledOnce()
  child.emit('exit', 1, null)
  expect(await call('status')).toMatchObject({ phase: 'error', detail: expect.stringContaining('Worker exited') })
})
