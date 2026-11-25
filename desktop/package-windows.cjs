const { existsSync } = require('node:fs')
const { join, resolve } = require('node:path')
const { Arch, build, Platform } = require('electron-builder')

const runtime = process.env.FARSTACK_RUNTIME_DIR
if (!runtime) throw new Error('Set FARSTACK_RUNTIME_DIR to the staged Windows runtime')
const runtimeDir = resolve(runtime)
if (!existsSync(join(runtimeDir, 'python.exe'))) throw new Error('The staged runtime is missing python.exe')

const config = {
  ...require('./package.json').build,
  extraResources: [{ from: runtimeDir, to: 'farstack-runtime' }],
}
build({ projectDir: __dirname, config, targets: Platform.WINDOWS.createTarget(['nsis'], Arch.x64), publish: 'never' })
  .catch(error => { console.error(error); process.exitCode = 1 })
