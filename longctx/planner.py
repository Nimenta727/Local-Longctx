"""Strict text-chat request admission; no automatic truncation or RAG."""
from dataclasses import dataclass

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
        raise RequestError("tool calls not supported in v0.1")
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
    # Count template-rendered text using the same model's tokenizer.
    # add_special plus a small margin is conservative, not a proof of identical
    # tokenization across upstream versions. Compare actual usage in benchmarks.
    rendered = backend.json("/apply-template", {"messages": messages})
    prompt = rendered.get("prompt")
    if not isinstance(prompt, str):
        raise RequestError("backend did not return a rendered prompt")
    tokens = backend.json("/tokenize", {"content": prompt,
                          "add_special": True, "parse_special": True}).get("tokens")
    if not isinstance(tokens, list) or not all(type(t) is int for t in tokens):
        raise RequestError("backend tokenizer returned unexpected response")
    if len(tokens) + output + 16 > c.context:
        raise RequestError("context budget exceeded; no automatic truncation")
    outbound = {k: v for k, v in body.items()
                if k not in ("max_completion_tokens", "tools", "tool_choice")}
    outbound["max_tokens"] = output
    return Plan(len(tokens), output, c.context, c.mode), outbound
