/** Read-only host bridge, using Harness's existing provider credential.
 * No transcript, tool payload or raw session identifier leaves the host.
 */
type CredentialAccess={resolve(ref:string):Promise<{value?:unknown}|undefined>}
export async function observeLocalAce(ctx:unknown,contextTokens:number,rangeTokens:number,signal:AbortSignal):Promise<string> {
  try {
    if(typeof ctx!=='object'||ctx===null) return 'unavailable'
    const get=Reflect.get(ctx,'get')
    if(typeof get!=='function') return 'unavailable'
    const credentials=Reflect.apply(get,ctx,['credentials']) as CredentialAccess|undefined
    if(!credentials||typeof credentials.resolve!=='function') return 'unavailable'
    const hit=await credentials.resolve('LOCAL_LONGCTX_API_KEY')
    if(typeof hit?.value!=='string'||signal.aborted) return 'unavailable'
    const response=await fetch('http://127.0.0.1:18080/local/ace/harness-plan',{
      method:'POST',redirect:'error',signal:AbortSignal.any([signal,AbortSignal.timeout(8000)]),
      headers:{Authorization:'Bearer '+hit.value,'Content-Type':'application/json'},
      body:JSON.stringify({context_tokens:contextTokens,range_tokens:rangeTokens})
    })
    if(!response.ok) return 'unavailable'
    const data:unknown=await response.json()
    if(typeof data==='object'&&data!==null&&'action' in data&&typeof data.action==='string'&&['observe','defer','keep'].includes(data.action)) return data.action
    return 'unavailable'
  }catch {return 'unavailable'}
}
