"""Native Anthropic Messages transport for local Harness.

The gateway validates and counts; the model proposes tool calls. Tool execution
and permission decisions remain exclusively in the Harness host.
"""
from .planner import Plan, RequestError
from .context import check_budget
from .backend import BackendError

PROMPT_FIELDS={"model","messages","system","thinking","tool_choice","tools"}
GEN_FIELDS=PROMPT_FIELDS|{"max_tokens","stream","metadata","stop_sequences","temperature","top_k","top_p"}

def fail(message):
    raise RequestError(message)

def text_blocks(content):
    if isinstance(content,str):
        return
    if not isinstance(content,list) or not content:
        fail("invalid text content")
    for b in content:
        if not isinstance(b,dict) or b.get("type")!="text" or not isinstance(b.get("text"),str):
            fail("only text blocks supported here")

def validate_prompt(body,c,count_only=False):
    if not isinstance(body,dict) or set(body)-(PROMPT_FIELDS if count_only else GEN_FIELDS):
        fail("unsupported Messages request fields")
    if body.get("model")!=c.model_id:
        fail("unknown model")
    if body.get("system") is not None:
        text_blocks(body["system"])
    messages=body.get("messages")
    if not isinstance(messages,list) or not messages:
        fail("nonempty messages required")
    tools=body.get("tools")
    if tools is None:
        tools=[]
    if not isinstance(tools,list):
        fail("invalid tools")
    names=set()
    for tool in tools:
        if (not isinstance(tool,dict) or set(tool)-{"name","description","input_schema","cache_control","type"}
            or tool.get("type","custom")!="custom"
            or not isinstance(tool.get("name"),str) or not tool["name"]
            or tool["name"] in names or not isinstance(tool.get("input_schema"),dict)):
            fail("invalid or duplicate client tool definition")
        names.add(tool["name"])
    choice=body.get("tool_choice")
    if choice is not None:
        if not isinstance(choice,dict) or set(choice)-{"type","name","disable_parallel_tool_use"} or choice.get("type") not in ("auto","any","tool","none"):
            fail("invalid tool choice")
        if choice.get("type")=="tool" and choice.get("name") not in names:
            fail("unknown selected tool")
        if choice.get("disable_parallel_tool_use"):
            fail("parallel tool restriction is not supported by this backend")
    pending=set()
    seen=set()
    for m in messages:
        if not isinstance(m,dict) or set(m)!={"role","content"} or m["role"] not in ("user","assistant"):
            fail("invalid message role or fields")
        role=m["role"]
        content=m["content"]
        if pending and role!="user":
            fail("missing tool results")
        if isinstance(content,str):
            if pending:
                fail("missing tool results")
            continue
        if not isinstance(content,list) or not content:
            fail("invalid message content")
        new_calls=set()
        for b in content:
            if not isinstance(b,dict):
                fail("invalid content block")
            kind=b.get("type")
            if kind=="text" and isinstance(b.get("text"),str):
                if pending:
                    fail("tool results must precede user text")
            elif kind=="thinking" and role=="assistant" and isinstance(b.get("thinking"),str):
                pass
            elif kind=="tool_use" and role=="assistant":
                ident=b.get("id")
                if not isinstance(ident,str) or not ident or ident in seen or not isinstance(b.get("name"),str) or not isinstance(b.get("input"),dict):
                    fail("invalid or duplicate tool call")
                seen.add(ident)
                new_calls.add(ident)
            elif kind=="tool_result" and role=="user":
                ident=b.get("tool_use_id")
                if not isinstance(ident,str) or ident not in pending:
                    fail("orphan or duplicate tool result")
                text_blocks(b.get("content",""))
                pending.remove(ident)
            else:
                fail("unsupported content block; images are not yet enabled")
        if pending:
            fail("incomplete tool result group")
        pending=new_calls
    if pending:
        fail("unanswered tool calls")
    return {k:v for k,v in body.items() if k in PROMPT_FIELDS}

def count_native(backend,prompt):
    n=backend.json("/v1/messages/count_tokens",prompt).get("input_tokens")
    if type(n) is not int or n<0:
        raise BackendError("invalid native token count")
    return n

def prepare_native(body,c,backend):
    prompt=validate_prompt(body,c)
    output=body.get("max_tokens")
    if type(output) is not int or not 1<=output<=c.output_reserve:
        fail("requested output exceeds configured reserve")
    if type(body.get("stream",False)) is not bool:
        fail("stream must be boolean")
    n=count_native(backend,prompt)
    try:
        check_budget(n,output,c.context,margin=256)
    except ValueError as exc:
        raise RequestError("maximum context window exceeded: " + str(exc)) from exc
    return Plan(n,output,c.context,"freetoken-native-messages"),dict(body)
