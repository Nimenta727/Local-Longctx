import { mkdir, readFile, readdir, realpath, rename, rm, stat, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { randomUUID } from 'node:crypto'
import { executeTool, toolDefinitions, workspaceFile } from './tools.mjs'
import { readToolStream } from './tool-stream.mjs'

const idPattern = /^[0-9a-f-]{36}$/i
const maxToolRounds=12
const maxCalls=8
const resultBlock=(id,{text,failed})=>({type:'tool_result',tool_use_id:id,content:text,...(failed?{is_error:true}:{})})

export function installConversations(ipc, owner, directory, connection, {chooseFolder,revealFile,request=fetch}) {
  let running
  let selectingWorkspace=false
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
  const publish=(window,session,event)=>{if(!window.isDestroyed())window.webContents.send('farstack:delta',{id:session.id,...event})}

  ipc.handle('farstack:conversation-list', async event => {
    owner(event)
    const names = await readdir(directory).catch(error => { if (error.code === 'ENOENT') return []; throw error })
    const entries = await Promise.all(names.filter(name => name.endsWith('.json') && idPattern.test(name.slice(0, -5)))
      .map(name => read(name.slice(0, -5)).catch(() => null)))
    return entries.filter(item => typeof item?.messages?.[0]?.content==='string')
      .map(item => ({ id: item.id, title: item.messages[0].content.slice(0, 60), updatedAt: item.updatedAt }))
      .sort((a, b) => b.updatedAt - a.updatedAt)
  })
  ipc.handle('farstack:conversation-load', (event, id) => { owner(event); return read(id) })
  ipc.handle('farstack:conversation-workspace', async (event,id) => {
    const window=owner(event)
    if(running||selectingWorkspace)throw new Error('请等待当前会话操作结束')
    selectingWorkspace=true
    try{
      const session=await read(id)
      const selected=await chooseFolder(window)
      if(selected){
        const workspace=await realpath(selected)
        if(session.workspace!==workspace)session.deliverables=[]
        session.workspace=workspace
        if(!(await stat(session.workspace)).isDirectory())throw new Error('请选择工作目录')
        await save(session)
      }
      return session
    } finally {selectingWorkspace=false}
  })
  ipc.handle('farstack:conversation-reveal',async(event,id,path)=>{
    owner(event)
    const session=await read(id)
    if(!session.workspace||!session.deliverables?.some(file=>file.path===path))throw new Error('这不是会话交付文件')
    await revealFile(await workspaceFile(session.workspace,path))
  })
  ipc.handle('farstack:conversation-cancel', event => { owner(event); running?.controller.abort() })
  ipc.handle('farstack:conversation-answer',(event,id,token,answer)=>{
    owner(event)
    const prompt=running?.prompt
    if(!prompt||running.id!==id||prompt.token!==token)throw new Error('这一条工具请求已结束')
    if(prompt.kind==='approval'&&typeof answer!=='boolean'||
       prompt.kind==='question'&&answer!==false&&(typeof answer!=='string'||!answer.trim()||answer.length>8000))
      throw new Error('回复为空或超过长度上限')
    prompt.resolve(answer)
  })

  ipc.handle('farstack:conversation-send', async (event, id, raw) => {
    const window=owner(event)
    if (running||selectingWorkspace) throw new Error('当前已有会话操作')
    if (typeof raw !== 'string' || !raw.trim() || Buffer.byteLength(raw) > 8 * 1024 * 1024) throw new Error('输入为空或超过单条消息上限')
    connection()
    const controller=new AbortController()
    const {signal}=controller
    const turn={id,controller}
    running=turn
    const ask=details=>new Promise(resolve=>{
      if(signal.aborted||window.isDestroyed()){resolve(false);return}
      const token=randomUUID()
      const cancel=()=>finish(false)
      const finish=answer=>{
        signal.removeEventListener('abort',cancel)
        turn.prompt=undefined
        publish(window,{id},{prompt:null})
        resolve(answer)
      }
      turn.prompt={token,kind:details.kind,resolve:finish}
      signal.addEventListener('abort',cancel,{once:true})
      publish(window,{id},{prompt:{...details,token}})
    })

    let session
    try {
      session=await read(id)
      session.messages.push({role:'user',content:raw})
      session.updatedAt=Date.now()
      await save(session)
      const known=new Set(session.messages.flatMap(message=>Array.isArray(message.content)
        ?message.content.filter(block=>block.type==='tool_use').map(block=>block.id):[]))
      for(let round=0;!signal.aborted&&round<=maxToolRounds;round++){
        const {key,output}=connection()
        const tools=round===maxToolRounds?[]:session.workspace?toolDefinitions:toolDefinitions.filter(tool=>
          tool.name==='todo_write'||tool.name==='ask_user_question')
        const response=await request('http://127.0.0.1:18080/v1/messages',{
          method:'POST',redirect:'error',signal,
          headers:{Authorization:'Bearer '+key,'Content-Type':'application/json','X-FarStack-Session':id},
          body:JSON.stringify({model:'local-longctx',max_tokens:output,messages:session.messages,stream:true,
            ...(tools.length?{tools}:{})}),
        })
        if(!response.ok){
          const error=await response.json().catch(()=>null)
          throw new Error(error?.error?.message??'生成请求失败 · HTTP '+response.status)
        }
        const {blocks,reason}=await readToolStream(response.body,text=>publish(window,session,{text}))
        const results=[]
        let count=0
        for(const block of blocks){
          if(block.type!=='tool_use')continue
          if(known.has(block.id))block.id='toolu_'+randomUUID()
          known.add(block.id)
          const invalid=block.invalid
          delete block.invalid
          let outcome
          if(signal.aborted)outcome={text:'用户已停止生成',failed:true}
          else if(invalid||reason!=='tool_use')outcome={text:'工具参数不完整，未执行',failed:true}
          else if(++count>maxCalls||!tools.some(tool=>tool.name===block.name))outcome={text:'工具不可用或已超过单轮调用上限',failed:true}
          else {
            publish(window,session,{tool:block.name})
            outcome=await executeTool(block,{
              workspace:session.workspace,ask,signal,
              setTodos:todos=>{session.todos=todos},
              present:files=>{
                const knownFiles=new Map((session.deliverables??[]).map(file=>[file.path,file]))
                for(const file of files)knownFiles.set(file.path,file)
                session.deliverables=[...knownFiles.values()].slice(-30)
              },
            })
          }
          results.push(resultBlock(block.id,outcome))
        }
        if(blocks.length)session.messages.push({role:'assistant',content:blocks})
        if(results.length)session.messages.push({role:'user',content:results})
        session.updatedAt=Date.now()
        await save(session)
        publish(window,session,{messages:session.messages,tool:null,todos:session.todos,deliverables:session.deliverables})
        if(!results.length||reason!=='tool_use')break
        if(round===maxToolRounds)throw new Error('已达到本轮的工具调用上限')
      }
    } catch(error) {
      if(error.partialText&&session){
        session.messages.push({role:'assistant',content:error.partialText})
        session.updatedAt=Date.now()
        await save(session)
      }
      if(!signal.aborted)throw error
    } finally {running=undefined}
    return session
  })
  return () => running?.controller.abort()
}
