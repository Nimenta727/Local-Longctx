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
    for name,dest in (("LocalLongctxPanel.tsx",CARD),("local-longctx-ipc.ts","apps/desktop/src/")):
        target=root/dest/name
        if target.exists():
            raise RuntimeError("overlay destination already exists")
        shutil.copyfile(ROOT/"overlay"/name,target)
    modify(root,CARD+"ModelsSection.tsx",[
        ("import { useId, useState } from 'react'","import { useId, useState } from 'react'\nimport { LocalLongctxPanel } from './LocalLongctxPanel.tsx'"),
        ("return (\n    <div className={styles['section']}>","return (\n    <div className={styles['section']}>\n      <LocalLongctxPanel />")])
    modify(root,CARD+"CustomProviderCard.tsx",[
        ("import { useEffect, useState } from 'react'","import { useEffect, useState } from 'react'\nimport { localLongctxBridge } from './LocalLongctxPanel.tsx'"),
        ("  return (\n    <div className={styles['editor']}>","""  const local = localLongctxBridge()
  const useLocal = async (): Promise<void> => {
    if (!local || profileDisabled || listBusy || taken.includes('local-longctx')) return
    if (!protocols.includes('openai-completions')) { setFailure('OpenAI completions protocol unavailable'); return }
    setBusy(true)
    try {
      const c = await local.connection()
      setRoute('local-longctx')
      setDisplayName('Local-Longctx')
      setBaseURL(c.baseURL)
      setProtocol('openai-completions')
      setKeyDraft(c.key)
      setModels([{id:c.model,name:'Local-Longctx',contextWindow:c.context,maxTokens:c.output,input:['text']}])
      setFailure(undefined)
    } catch (e) { setFailure(String(e)) }
    finally { setBusy(false) }
  }
  return (
    <div className={styles['editor']}>
      {local ? <button type="button" disabled={profileDisabled || listBusy || taken.includes('local-longctx')} onClick={()=>{void useLocal()}}>Local-Longctx 本地模型预设 / Local model preset</button> : null}""")])
    modify(root,"apps/desktop/src/main.ts",[
        ("import { installFileActions } from './file-actions.ts'","import { installFileActions } from './file-actions.ts'\nimport { installLocalLongctx } from './local-longctx-ipc.ts'"),
        ("  ipcMain.handle(DESKTOP_IPC.boot, async (event) => {","  installLocalLongctx(assertProductSender)\n  ipcMain.handle(DESKTOP_IPC.boot, async (event) => {")])
    modify(root,"apps/desktop/src/preload-app.ts",[
        ("markDocumentPlatform()","""if (location.protocol === `${SCHEME}:` && location.hostname === 'app' && process.isMainFrame) {
  contextBridge.exposeInMainWorld('localLongctx', {
    status: () => ipcRenderer.invoke('local-longctx:status'),
    pick: (kind: 'model' | 'engine') => ipcRenderer.invoke('local-longctx:pick', kind),
    start: (settings: unknown) => ipcRenderer.invoke('local-longctx:start', settings),
    stop: () => ipcRenderer.invoke('local-longctx:stop'),
    connection: () => ipcRenderer.invoke('local-longctx:connection'),
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
