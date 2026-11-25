import { mkdir, readFile, readdir, rename, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { randomUUID } from 'node:crypto'

const idPattern = /^[0-9a-f-]{36}$/i

export function installConversations(ipc, owner, directory, connection) {
  let running
  const filename = id => {
    if (typeof id !== 'string' || !idPattern.test(id)) throw new Error('无效的会话标识')
    return join(directory, id + '.json')
  }
  const read = async id => {
    try { return JSON.parse(await readFile(filename(id), 'utf8')) }
    catch (error) { if (error.code === 'ENOENT') return { id, messages: [] }; throw error }
  }
  const save = async data => {
    await mkdir(directory, { recursive: true, mode: 0o700 })
    const target = filename(data.id)
    const temp = target + '.' + randomUUID() + '.tmp'
    try {
      await writeFile(temp, JSON.stringify(data), { flag: 'wx', mode: 0o600 })
      await rename(temp, target)
    } finally { await rm(temp, { force: true }) }
  }

  ipc.handle('farstack:conversation-list', async event => {
    owner(event)
    const names = await readdir(directory).catch(error => { if (error.code === 'ENOENT') return []; throw error })
    const entries = await Promise.all(names.filter(name => name.endsWith('.json') && idPattern.test(name.slice(0, -5)))
      .map(name => read(name.slice(0, -5)).catch(() => null)))
    return entries.filter(item => item?.messages.length)
      .map(item => ({ id: item.id, title: item.messages[0].content.slice(0, 60), updatedAt: item.updatedAt }))
      .sort((a, b) => b.updatedAt - a.updatedAt)
  })
  ipc.handle('farstack:conversation-load', (event, id) => {
    owner(event)
    return read(id)
  })
  ipc.handle('farstack:conversation-cancel', event => { owner(event); running?.abort() })
  ipc.handle('farstack:conversation-send', async (event, id, raw) => {
    const window = owner(event)
    if (running) throw new Error('当前已有生成请求')
    if (typeof raw !== 'string' || !raw.trim() || Buffer.byteLength(raw) > 8 * 1024 * 1024) throw new Error('输入为空或超过单条消息上限')
    const {key, output} = connection()
    const controller = new AbortController()
    running = controller
    let content = ''
    let session
    try {
      session = await read(id)
      session.messages.push({ role: 'user', content: raw })
      session.updatedAt = Date.now()
      await save(session)
      const response = await fetch('http://127.0.0.1:18080/v1/messages', {
        method: 'POST', redirect: 'error', signal: controller.signal,
        headers: { Authorization: 'Bearer ' + key, 'Content-Type': 'application/json', 'X-FarStack-Session': id },
        body: JSON.stringify({ model: 'local-longctx', max_tokens: output, messages: session.messages, stream: true }),
      })
      if (!response.ok) {
        const error = await response.json().catch(() => null)
        throw new Error(error?.error?.message ?? '生成请求失败 · HTTP ' + response.status)
      }
      const decoder = new TextDecoder()
      let pending = ''
      let completed = false
      for await (const chunk of response.body) {
        const lines = (pending + decoder.decode(chunk, { stream: true })).split('\n')
        pending = lines.pop()
        if (pending.length > 2 ** 20) throw new Error('生成响应超过单帧上限')
        for (const line of lines) {
          if (!line.startsWith('data:')) continue
          const payload = JSON.parse(line.slice(5))
          if (payload.type === 'error') throw new Error(payload.error?.message ?? '推理引擎报告错误')
          if (payload.type === 'message_stop') completed = true
          const text = payload.delta?.type === 'text_delta' ? payload.delta.text : undefined
          if (typeof text === 'string') {
            content += text
            if (!window.isDestroyed()) window.webContents.send('farstack:delta', { id, text })
          }
        }
      }
      if (!completed) throw new Error('生成中断，已收到的内容保留在本地')
    } catch (error) {
      if (!controller.signal.aborted) throw error
    } finally {
      try {
        if (content && session) {
          session.messages.push({ role: 'assistant', content })
          session.updatedAt = Date.now()
          await save(session)
        }
      } finally { running = undefined }
    }
    return session
  })
  return () => running?.abort()
}
