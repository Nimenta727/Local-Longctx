// Assemble the native Messages SSE blocks before dispatching any tool call.
export async function readToolStream(body,onText) {
  const decoder=new TextDecoder()
  const active=new Map(), completed=new Map()
  let pending='', stopped=false, reason, text=''
  function event(line) {
    if(!line.startsWith('data:'))return
    const payload=JSON.parse(line.slice(5))
    const {type,index,delta}=payload
    if(type==='error')throw new Error(payload.error?.message??'推理引擎报告错误')
    if(type==='message_stop'){stopped=true;return}
    if(type==='message_delta'){reason=delta?.stop_reason??reason;return}
    if(type==='content_block_start'){
      if(!Number.isSafeInteger(index)||index<0||index>255||active.has(index)||completed.has(index))
        throw new Error('无效的模型输出块')
      const block=payload.content_block
      if(block?.type==='tool_use')active.set(index,{block,partial:''})
      else if(block?.type==='thinking')active.set(index,{block:{type:'thinking',thinking:String(block.thinking??'')}})
      else if(block?.type==='text'){
        const data={type:'text',text:String(block.text??'')}
        active.set(index,{block:data})
        if(data.text){text+=data.text;onText(data.text)}
      } else active.set(index,{block:null})
      return
    }
    if(type==='content_block_delta'){
      const item=active.get(index)
      if(!item)throw new Error('模型输出块次序有误')
      if(delta?.type==='text_delta'&&item.block?.type==='text'&&typeof delta.text==='string'){
        item.block.text+=delta.text
        text+=delta.text
        onText(delta.text)
      } else if(delta?.type==='input_json_delta'&&item.block?.type==='tool_use'&&typeof delta.partial_json==='string'){
        item.partial+=delta.partial_json
        if(item.partial.length>1024*1024)throw new Error('工具参数超过大小限制')
      } else if(delta?.type==='thinking_delta'&&item.block?.type==='thinking'&&typeof delta.thinking==='string'){
        item.block.thinking+=delta.thinking
      }
      return
    }
    if(type==='content_block_stop'){
      const item=active.get(index)
      if(!item)throw new Error('模型输出块次序有误')
      active.delete(index)
      const {block,partial}=item
      if(block?.type==='tool_use'){
        if(typeof block.id!=='string'||!block.id||typeof block.name!=='string'||!block.name)
          throw new Error('无效的工具调用标识')
        let input=block.input
        if(partial)try{input=JSON.parse(partial)}catch{input=null}
        const valid=input && typeof input==='object' && !Array.isArray(input)
        completed.set(index,{type:'tool_use',id:block.id,name:block.name,input:valid?input:{},invalid:!valid})
      } else completed.set(index,block)
    }
  }
  try {
    for await (const chunk of body) {
      const lines=(pending+decoder.decode(chunk,{stream:true})).split('\n')
      pending=lines.pop()
      if(pending.length>2**20)throw new Error('生成响应超过单帧上限')
      for(const line of lines)event(line)
      if(stopped)break
    }
    if(!stopped)event(pending+decoder.decode())
    if(!stopped||active.size)throw new Error('生成中断，已收到的文本保留在本地')
    return {blocks:[...completed.entries()].sort(([a],[b])=>a-b).map(([,block])=>block).filter(Boolean),reason}
  } catch(error) {
    const failure=new Error(error.message,{cause:error})
    failure.partialText=text
    throw failure
  }
}
