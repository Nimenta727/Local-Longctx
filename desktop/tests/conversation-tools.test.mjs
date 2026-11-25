import assert from 'node:assert/strict'
import { mkdtemp, readFile, realpath, rm, symlink, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test } from 'node:test'
import { installConversations } from '../app/conversations.mjs'

const sessionId='01234567-89ab-cdef-0123-456789abcdef'
function stream(blocks,reason='end_turn',finish=true){
  const events=[]
  for(const [index,block] of blocks.entries()){
    const tool=block.type==='tool_use'
    events.push({type:'content_block_start',index,content_block:tool?{...block,input:{}}:{type:'text',text:''}})
    const source=tool?JSON.stringify(block.input):block.text
    const midpoint=Math.ceil(source.length/2)
    for(const part of [source.slice(0,midpoint),source.slice(midpoint)]){
      events.push({type:'content_block_delta',index,delta:tool?{type:'input_json_delta',partial_json:part}:{type:'text_delta',text:part}})
    }
    events.push({type:'content_block_stop',index})
  }
  events.push({type:'message_delta',delta:{stop_reason:reason}})
  if(finish)events.push({type:'message_stop'})
  const bytes=Buffer.from(events.map(event=>'data: '+JSON.stringify(event)+'\r\n\r\n').join(''))
  let offset=0
  return new Response(new ReadableStream({pull(controller){
    if(offset>=bytes.length){controller.close();return}
    controller.enqueue(bytes.subarray(offset,offset+=11))
  }}))
}
const call=(id,name,input)=>({type:'tool_use',id,name,input})
async function fixture(t, request, onPrompt){
  const root=await realpath(await mkdtemp(join(tmpdir(),'farstack-workspace-')))
  const data=await mkdtemp(join(tmpdir(),'farstack-session-'))
  t.after(()=>Promise.all([root,data].map(path=>rm(path,{recursive:true,force:true}))))
  const handlers=new Map(), events=[], revealed=[]
  const invoke=(name,...args)=>handlers.get('farstack:conversation-'+name)(null,...args)
  const window={isDestroyed:()=>false,webContents:{send(_,event){
    events.push(event)
    if(event.prompt)onPrompt?.(event.prompt,invoke)
  }}}
  installConversations({handle:(name,fn)=>handlers.set(name,fn)},()=>window,data,()=>({key:'local',output:256}),
    {chooseFolder:()=>root,revealFile:path=>revealed.push(path),request})
  await invoke('workspace',sessionId)
  return {root,invoke,events,revealed}
}

test('local tool turns return approved results, denied results and user input; session reloads',async t=>{
  const requests=[]
  const {root,invoke,events,revealed}=await fixture(t,async(_url,options)=>{
    const body=JSON.parse(options.body)
    requests.push(body)
    if(requests.length===1)return stream([
      call('write','write',{file_path:'done.txt',content:'完成\n'}),
      call('denied','write',{file_path:'blocked.txt',content:'拒绝'}),
      call('read','read',{file_path:'done.txt'}),
      call('todo','todo_write',{todos:[{content:'写文件',status:'completed'}]}),
      call('ask','ask_user_question',{question:'用中文总结吗？'}),
      call('present','present',{files:[{path:'done.txt',description:'交付'}]}),
    ],'tool_use')
    return stream([{type:'text',text:'全部完成。'}])
  },(prompt,invoke)=>{
    const answer=prompt.kind==='question'?'用中文':!prompt.detail.includes('blocked.txt')
    invoke('answer',sessionId,prompt.token,answer)
  })
  const session=await invoke('send',sessionId,'完成任务')
  assert.equal(await readFile(join(root,'done.txt'),'utf8'),'完成\n')
  await assert.rejects(readFile(join(root,'blocked.txt')), {code:'ENOENT'})
  assert.equal(requests.length,2)
  assert.equal(requests[0].tools.some(tool=>tool.name==='grep'),true)
  const results=requests[1].messages.at(-1).content
  assert.deepEqual(results.map(result=>result.tool_use_id),['write','denied','read','todo','ask','present'])
  assert.equal(results[1].is_error,true)
  assert.match(results[2].content,/完成/)
  assert.equal(results[4].content,'用中文')
  assert.equal(session.messages.at(-1).content[0].text,'全部完成。')
  assert.deepEqual(session.todos,[{content:'写文件',status:'completed'}])
  assert.deepEqual(await invoke('load',sessionId),session)
  assert.equal((await invoke('list'))[0].title,'完成任务')
  await invoke('reveal',sessionId,'done.txt')
  assert.deepEqual(revealed,[join(root,'done.txt')])
  await assert.rejects(invoke('reveal',sessionId,'../outside'),/不是会话交付文件/)
  assert.equal(events.filter(event=>event.prompt).length,3)
})

test('an incomplete stream never runs tools and cancellation clears a pending approval',async t=>{
  let index=0
  const {root,invoke}=await fixture(t,async()=>{
    index++
    return stream([call('write','write',{file_path:'never.txt',content:'forbidden'})],'tool_use',index===2)
  },(_prompt,invoke)=>invoke('cancel'))
  await assert.rejects(invoke('send',sessionId,'stream stops'),/生成中断/)
  let stored=await invoke('load',sessionId)
  assert.equal(stored.messages.length,1)
  await invoke('send',sessionId,'cancel')
  stored=await invoke('load',sessionId)
  assert.equal(stored.messages.at(-1).content[0].is_error,true)
  await assert.rejects(readFile(join(root,'never.txt')), {code:'ENOENT'})
})

test('workspace search and edit work, and paths outside it are rejected',async t=>{
  const requests=[]
  const {root,invoke}=await fixture(t,async(_url,options)=>{
    requests.push(JSON.parse(options.body))
    if(requests.length===1)return stream([
      call('glob','glob',{pattern:'**/*.txt'}),
      call('grep','grep',{pattern:'needle',glob:'**/*.txt'}),
      call('edit','edit',{file_path:'inside.txt',old_string:'needle',new_string:'updated'}),
      call('parent','read',{file_path:'../outside.txt'}),
      call('symlink','read',{file_path:'link.txt'}),
    ],'tool_use')
    return stream([{type:'text',text:'完成'}])
  },(prompt,invoke)=>invoke('answer',sessionId,prompt.token,true))
  const path=join(root,'inside.txt')
  await writeFile(path,'needle\n')
  if(process.platform!=='win32')await symlink(path,join(root,'link.txt'))
  await invoke('send',sessionId,'查找')
  const results=requests[1].messages.at(-1).content
  assert.equal(results[0].content,'inside.txt')
  assert.match(results[1].content,/inside\.txt:1: needle/)
  assert.equal(await readFile(path,'utf8'),'updated\n')
  assert.equal(results[3].is_error,true)
  assert.equal(results[4].is_error,true)
})

test('a local shell command only runs after confirmation and returns stdout',async t=>{
  let index=0
  const name=process.platform==='win32'?'pwsh':'bash'
  const command=process.platform==='win32'?"Write-Output 'farstack-tool'":"printf 'farstack-tool'"
  const {invoke}=await fixture(t,async(_url,options)=>{
    index++
    if(index===1)return stream([call('command',name,{command,description:'Print test text'})],'tool_use')
    const result=JSON.parse(options.body).messages.at(-1).content[0]
    assert.match(result.content,/^退出码 0\n/)
    assert.match(result.content,/^farstack-tool\r?$/m)
    assert.equal(result.is_error,undefined)
    return stream([{type:'text',text:'命令完成'}])
  },(prompt,invoke)=>{
    assert.match(prompt.detail,/farstack-tool/)
    invoke('answer',sessionId,prompt.token,true)
  })
  await invoke('send',sessionId,'运行本地测试命令')
  assert.equal(index,2)
})
