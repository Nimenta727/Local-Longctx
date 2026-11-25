import { spawn } from 'node:child_process'
import { constants } from 'node:fs'
import { lstat, open, readdir, realpath, rename, rm, writeFile } from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
import { dirname, isAbsolute, join, posix, relative, resolve, sep } from 'node:path'

const maxFile = 1024 * 1024
const maxResult = 64000
const shell = process.platform === 'win32' ? 'pwsh' : 'bash'
const list = {
  read: ['Read lines from a workspace text file.', {file_path:'string',offset:'integer',limit:'integer'}, ['file_path']],
  write: ['Create or replace a workspace text file after user approval.', {file_path:'string',content:'string'}, ['file_path','content']],
  edit: ['Replace one exact occurrence in a workspace file after user approval.', {file_path:'string',old_string:'string',new_string:'string'}, ['file_path','old_string','new_string']],
  glob: ['List workspace files by a relative glob pattern.', {pattern:'string'}, ['pattern']],
  grep: ['Search workspace text files for a literal string.', {pattern:'string',glob:'string'}, ['pattern']],
  [shell]: ['Run a local development command in the selected workspace after approval. Use absolute paths only if explicitly requested by the user.', {command:'string',description:'string'}, ['command']],
  todo_write: ['Replace the visible task list. Status values are pending, in_progress and completed.', {todos:'array'}, ['todos']],
  present: ['Show existing workspace files as deliverables to the user.', {files:'array'}, ['files']],
  ask_user_question: ['Ask the user a question and wait for an answer.', {question:'string'}, ['question']],
}
export const toolDefinitions = Object.entries(list).map(([name,[description,fields,required]]) => ({
  name,description,input_schema:{type:'object',properties:Object.fromEntries(
    Object.entries(fields).map(([field,type])=>[field,type==='array'?{type,items:{type:'object',
      properties:field==='todos'?{content:{type:'string'},status:{enum:['pending','in_progress','completed']}}
        :{path:{type:'string'},description:{type:'string'}},
      required:field==='todos'?['content','status']:['path'],additionalProperties:false}}:{type}])
  ),required,additionalProperties:false},
}))

const clip = value => value.length > maxResult ? value.slice(0,maxResult) + '\n[输出已截取]' : value
const normalize = path => path.split(sep).join('/')
const safePart = part => part && part!=='.' && part!=='..' && !/[\x00-\x1f:]/.test(part) &&
  !(/[ .]$/.test(part)) && !/^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(part)

export async function workspaceFile(root, path, create = false) {
  if(await realpath(root)!==root)throw new Error('工作目录已改变，请重新选择')
  if (typeof path!=='string' || isAbsolute(path) || !path.split(/[/\\]/).every(safePart))
    throw new Error('请输入有效的工作目录相对路径')
  const parts=path.split(/[/\\]/)
  let current=root
  for (const [index,part] of parts.entries()) {
    if (part.toLowerCase()==='.git') throw new Error('无法访问 Git 元数据目录')
    current=join(current,part)
    const entry=await lstat(current).catch(error=>{
      if (error.code==='ENOENT' && create && index===parts.length-1) return null
      throw error
    })
    if (!entry) return current
    if (entry.isSymbolicLink() || (index===parts.length-1 ? !entry.isFile() : !entry.isDirectory()))
      throw new Error('路径必须指向工作目录内的常规文件')
    const rel=relative(root,await realpath(current))
    if (isAbsolute(rel)||rel==='..'||rel.startsWith('..'+sep)) throw new Error('路径超出工作目录')
  }
  return current
}

async function readText(path) {
  const file=await open(path,constants.O_RDONLY|(constants.O_NOFOLLOW??0))
  try {
    const stat=await file.stat()
    if(!stat.isFile()||stat.nlink!==1||stat.size>maxFile) throw new Error('仅支持 1 MiB 以内、没有硬链接的普通文本文件')
    const bytes=Buffer.alloc(maxFile+1)
    let count=0
    while(count<bytes.length){
      const {bytesRead}=await file.read(bytes,count,bytes.length-count,count)
      if(!bytesRead)break
      count+=bytesRead
    }
    if(count>maxFile||bytes.subarray(0,count).includes(0)) throw new Error('文件超过上限或不是文本')
    return new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes.subarray(0,count))
  } finally { await file.close() }
}

async function replaceFile(root,path,text) {
  const destination=await workspaceFile(root,path,true)
  const mode=await lstat(destination).then(stat=>stat.mode&0o777,error=>{
    if(error.code==='ENOENT') return 0o600
    throw error
  })
  const temp=join(dirname(destination),'.farstack-'+randomUUID()+'.tmp')
  try {
    await writeFile(temp,text,{flag:'wx',mode})
    await workspaceFile(root,path,true)
    await rename(temp,destination)
  } finally {await rm(temp,{force:true})}
  return '已保存 '+path
}

function matcher(pattern) {
  if(typeof pattern!=='string'||!pattern||pattern.length>300||(pattern.match(/\*+/g)?.length??0)>8)
    throw new Error('无效的文件匹配模式')
  const fold = path => process.platform==='win32'?path.toLowerCase():path
  const glob=fold(pattern.replaceAll('\\','/'))
  return path=>posix.matchesGlob(fold(path),glob)
}

async function scan(root,args,name,signal) {
  const matches=matcher(name==='glob'?args.pattern:args.glob??'**/*')
  if(name==='grep'&&(!args.pattern||args.pattern.length>1024))throw new Error('搜索文本长度必须在 1 至 1024 字符之间')
  const queue=[root], results=[]
  let visited=0
  while(queue.length&&visited<10000&&results.length<200){
    signal.throwIfAborted()
    for(const entry of await readdir(queue.pop(),{withFileTypes:true})){
      signal.throwIfAborted()
      if(++visited>10000||results.length>=200)break
      if(!safePart(entry.name)||['.git','node_modules','.venv','__pycache__'].includes(entry.name.toLowerCase()))continue
      const path=resolve(entry.parentPath,entry.name)
      const nameInRoot=normalize(relative(root,path))
      if(entry.isDirectory()){
        if(await realpath(path).catch(()=>null)!==path)continue
        queue.push(path)
      } else if(entry.isFile()&&matches(nameInRoot)){
        if(name==='glob'){results.push(nameInRoot);continue}
        const content=await workspaceFile(root,nameInRoot).then(readText).catch(()=>null)
        if(content===null)continue
        for(const [index,line] of content.split(/\r?\n/).entries()){
          if(line.includes(args.pattern))results.push(nameInRoot+':'+(index+1)+': '+line.slice(0,500))
          if(results.length>=200)break
        }
      }
    }
  }
  return results.join('\n')+(visited>=10000||results.length>=200?'\n[已达到扫描或匹配上限]':'')||'没有匹配项。'
}

function runCommand(root,command,signal) {
  signal.throwIfAborted()
  const windows=process.platform==='win32'
  const executable=windows
    ?join(process.env.SystemRoot??'C:\\Windows','System32','WindowsPowerShell','v1.0','powershell.exe')
    :'/bin/bash'
  const windowsFlags=()=> {
    const script='$ProgressPreference = "SilentlyContinue"; [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false); '+command
    return ['-NoLogo','-NoProfile','-NonInteractive','-OutputFormat','Text','-EncodedCommand',Buffer.from(script,'utf16le').toString('base64')]
  }
  const flags=windows?windowsFlags():['--noprofile','--norc','-c',command]
  return new Promise((resolve,reject)=>{
    const env={...process.env}
    delete env.BASH_ENV
    delete env.ENV
    const child=spawn(executable,flags,{cwd:root,env,windowsHide:true,detached:!windows,
      stdio:['ignore','pipe','pipe']})
    let output='', truncated=false, finished=false
    const collect=text=>{
      if(output.length+text.length>maxResult)truncated=true
      output+=text.slice(0,Math.max(0,maxResult-output.length))
    }
    for(const stream of [child.stdout,child.stderr])stream.setEncoding('utf8').on('data',collect)
    const settle=(error,value)=>{
      if(finished)return
      finished=true
      clearTimeout(timer)
      signal.removeEventListener('abort',stop)
      if(error)reject(error)
      else resolve(value)
    }
    const stop=()=>{
      if(child.pid)try{
        if(windows){
          const taskkill=join(process.env.SystemRoot??'C:\\Windows','System32','taskkill.exe')
          const kill=spawn(taskkill,['/pid',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'})
          kill.on('error',()=>child.kill())
        } else process.kill(-child.pid,'SIGKILL')
      }catch{child.kill()}
      child.stdout.destroy()
      child.stderr.destroy()
      settle(new Error(signal.aborted?'命令已停止':'命令超过 60 秒时限'))
    }
    const timer=setTimeout(stop,60000)
    signal.addEventListener('abort',stop,{once:true})
    child.on('error',error=>settle(error))
    child.on('close',code=>settle(null,{failed:code!==0,text:'退出码 '+code+'\n'+output+(truncated?'\n[输出已截取]':'')}))
  })
}

const isObject = value => value && typeof value==='object' && !Array.isArray(value)
function validated(name,args){
  if(!Object.hasOwn(list,name)||!isObject(args))throw new Error('未知工具或无效参数')
  const [,fields,required]=list[name]
  for(const field of required)if(!Object.hasOwn(args,field))throw new Error('缺少参数 '+field)
  for(const [field,value] of Object.entries(args)){
    const type=fields[field]
    if(!Object.hasOwn(fields,field)||(type==='array'?!Array.isArray(value):type==='integer'?!Number.isSafeInteger(value):typeof value!==type))
      throw new Error('无效参数 '+field)
  }
  return args
}

export async function executeTool(call,{workspace,ask,setTodos,present,signal}) {
  try {
    signal.throwIfAborted()
    const {name}=call
    const args=validated(name,call.input)
    if(name==='todo_write'){
      if(args.todos.length>30||args.todos.some(item=>!isObject(item)||typeof item.content!=='string'||!item.content.trim()||
        item.content.length>400||!['pending','in_progress','completed'].includes(item.status)))throw new Error('无效的任务列表')
      setTodos(args.todos.map(({content,status})=>({content,status})))
      return {text:'任务列表已更新'}
    }
    if(name==='ask_user_question'){
      if(!args.question.trim()||args.question.length>2000)throw new Error('问题为空或过长')
      const answer=await ask({kind:'question',title:'本地模型提问',detail:args.question})
      if(!answer)throw new Error('用户跳过了这个问题')
      return {text:answer}
    }
    if(!workspace)throw new Error('请先在会话中选择工作目录')
    if(await realpath(workspace)!==workspace)throw new Error('工作目录已改变，请重新选择')
    if(name==='present'){
      if(!args.files.length||args.files.length>4||args.files.some(file=>!isObject(file)||typeof file.path!=='string'||
        (file.description!==undefined&&(typeof file.description!=='string'||file.description.length>400))))
        throw new Error('请选择 1 至 4 个工作目录内的文件')
      for(const file of args.files)await workspaceFile(workspace,file.path)
      present(args.files.map(({path,description})=>({path,description})))
      return {text:args.files.map(file=>'已展示 '+file.path).join('\n')}
    }
    if(name==='glob'||name==='grep')return {text:clip(await scan(workspace,args,name,signal))}
    if(name===shell){
      if(!args.command.trim()||args.command.length>12000)throw new Error('命令为空或过长')
      if(!await ask({kind:'approval',title:'允许运行命令？',
        detail:workspace+'\n\n'+args.command+'\n\n命令以当前账户权限运行。'}))throw new Error('用户拒绝了命令')
      return await runCommand(workspace,args.command,signal)
    }
    const path=await workspaceFile(workspace,args.file_path,name==='write')
    if(name==='read'){
      const start=args.offset??1, limit=args.limit??200
      if(start<1||limit<1||limit>1000)throw new Error('起始行至少为 1，读取范围为 1 至 1000 行')
      const lines=(await readText(path)).split(/\r?\n/)
      return {text:clip(lines.slice(start-1,start-1+limit).map((line,i)=>(start+i)+': '+line).join('\n')||'没有可读取的行。')}
    }
    const previous=name==='edit'?await readText(path):null
    let content=args.content
    if(name==='edit'){
      const index=previous.indexOf(args.old_string)
      if(!args.old_string||index<0||previous.indexOf(args.old_string,index+1)>=0)throw new Error('旧文本必须恰好出现一次')
      content=previous.slice(0,index)+args.new_string+previous.slice(index+args.old_string.length)
    }
    if(Buffer.byteLength(content)>maxFile)throw new Error('保存内容超过 1 MiB')
    const preview=name==='edit'?'原文\n'+args.old_string+'\n\n替换为\n'+args.new_string:content
    if(!await ask({kind:'approval',title:'允许修改文件？',detail:path+'\n\n'+preview.slice(0,12000)+
      (preview.length>12000?'\n[预览已截取]':'')}))
      throw new Error('用户拒绝了文件修改')
    signal.throwIfAborted()
    if(previous!==null&&previous!==await readText(await workspaceFile(workspace,args.file_path)))
      throw new Error('文件在确认期间已改变，请重新读取')
    return {text:await replaceFile(workspace,args.file_path,content)}
  } catch(error) {
    return {text:clip(String(error.message??error)),failed:true}
  }
}
