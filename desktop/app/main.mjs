import { app, BrowserWindow, net, protocol } from 'electron'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { join } from 'node:path'
import { installRuntime } from './runtime.mjs'

app.setName('FarStack')
protocol.registerSchemesAsPrivileged([{scheme:'farstack',privileges:{standard:true,secure:true,supportFetchAPI:true}}])
if (process.env.FARSTACK_USER_DATA) app.setPath('userData', process.env.FARSTACK_USER_DATA)

if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  const page = 'farstack://workspace/index.html'
  let window
  app.on('second-instance', () => {
    if (window?.isMinimized()) window.restore()
    window?.focus()
  })
  app.whenReady().then(async () => {
    const assets=new Set(['/index.html','/workspace.mjs','/workspace.css','/farstack.png'])
    protocol.handle('farstack', request => {
      const url=new URL(request.url)
      if(url.hostname!=='workspace'||!assets.has(url.pathname))return new Response(null,{status:404})
      return net.fetch(pathToFileURL(join(import.meta.dirname,url.pathname.slice(1))).href)
    })
    window = new BrowserWindow({
      width: 1320, height: 970, minWidth: 720, minHeight: 580,
      title: '远栈 FarStack', backgroundColor: '#11151a',
      icon: fileURLToPath(new URL('./farstack.png', import.meta.url)),
      webPreferences: {
        preload: join(import.meta.dirname, 'preload.cjs'),
        sandbox: true, contextIsolation: true, nodeIntegration: false,
      },
    })
    installRuntime(event => {
      const frame = event.senderFrame
      if (event.sender !== window.webContents || !frame || frame !== window.webContents.mainFrame ||
          frame.url !== page) throw new Error('Untrusted desktop frame')
      return window
    })
    window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
    window.webContents.on('will-navigate', event => event.preventDefault())
    await window.loadURL(page)
  }).catch(error => {
    console.error('FarStack startup failed', error)
    app.exit(1)
  })
  app.on('window-all-closed', () => app.quit())
}
