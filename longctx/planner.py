"""Text request admission / 文本请求预算检查；不静默截断。"""
from dataclasses import dataclass
from .context import check_budget

class RequestError(ValueError):
    pass

@dataclass(frozen=True)
class Plan:
    prompt_tokens: int
    output_tokens: int
    total_limit: int
    mode: str

# Fields with verified or conventional chat-completions meanings only.
ALLOWED = {"model", "messages", "stream", "stream_options", "max_tokens",
           "max_completion_tokens", "temperature", "top_p", "stop", "seed",
           "frequency_penalty", "presence_penalty", "n", "tools", "tool_choice"}

def prepare(body, c, backend):
    if not isinstance(body, dict):
        raise RequestError("request must be a JSON object")
    unknown = set(body) - ALLOWED
    if unknown:
        raise RequestError("unsupported fields: " + ", ".join(sorted(unknown)))
    if body.get("model") != c.model_id:
        raise RequestError("unknown model")
    if body.get("tools") or body.get("tool_choice", "none") not in (None, "none", "auto"):
        raise RequestError("use native Messages for tool calling")
    if body.get("n", 1) != 1:
        raise RequestError("only one completion is supported")
    if type(body.get("stream", False)) is not bool:
        raise RequestError("stream must be boolean")
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise RequestError("messages must be a nonempty array")
    for m in messages:
        if (not isinstance(m, dict) or set(m) != {"role", "content"} or
                m["role"] not in ("system", "user", "assistant") or
                not isinstance(m["content"], str)):
            raise RequestError("only plain-text system/user/assistant messages supported")
    limits = [body[k] for k in ("max_tokens", "max_completion_tokens") if k in body]
    if len(limits) == 2 and limits[0] != limits[1]:
        raise RequestError("conflicting output limits")
    output = limits[0] if limits else c.output_reserve
    if type(output) is not int or not 1 <= output <= c.output_reserve:
        raise RequestError("requested output exceeds configured reserve")
    # Cross-API estimate; verify native template parity.
    count=backend.count_prompt(messages)
    try:
        check_budget(count,output,c.context,margin=256)
    except ValueError as exc:
        raise RequestError(str(exc)) from exc
    outbound={k:v for k,v in body.items() if k not in ("max_completion_tokens","tools","tool_choice")}
    outbound["max_tokens"]=output
    return Plan(count,output,c.context,"freetoken-native-experimental"),outbound
