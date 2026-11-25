"""Small local concept vocabulary shared by the gateway and desktop overlay."""
import json
import re
from importlib.resources import files

PATTERNS = {
    name: re.compile("|".join(aliases), re.IGNORECASE | re.ASCII)
    for name, aliases in json.loads(
        files("longctx").joinpath("recall_concepts.json").read_text(encoding="utf-8")
    ).items()
}


def concepts(text):
    return [name for name, pattern in PATTERNS.items() if pattern.search(text)]
