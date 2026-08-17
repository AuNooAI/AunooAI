"""Tag routing-only alias entries in litellm_config.yaml with model_info.legacy_alias.

An entry is an alias when its model_name does not name the model its litellm target
actually runs. Decided per tenant from the target, so a tenant where gpt-5 really
routes to openai/gpt-5 keeps it visible. Applies by text insertion (never yaml.dump)
so comments and formatting survive.
"""
import re
import sys

import yaml

APPLY = "--apply" in sys.argv
paths = [a for a in sys.argv[1:] if a != "--apply"]

# Legacy duplicate names for the canonical claude-*-4-5 entries: truthful-ish but
# version-less and redundant next to the canonical names, so always tagged.
BLOCKLIST = {"bedrock-claude-haiku", "bedrock-claude-sonnet"}


def norm(s):
    return re.sub(r"[-._:]", "", s.lower())


def resolved_tail(target):
    t = target.split("/")[-1]
    t = re.sub(r"^(us|eu|apac)\.", "", t)
    t = re.sub(r"^(anthropic|meta|amazon|mistral|cohere|moonshotai)\.", "", t)
    t = re.sub(r"-\d{8}(-v\d+:\d+)?$", "", t)
    return t


def is_alias(name, target):
    if name in BLOCKLIST:
        return True
    tail = resolved_tail(target)
    n, t = norm(name), norm(tail)
    if n == t or t.startswith(n) or n.startswith(t):
        return False
    if norm(name.replace("bedrock-", "")) in (t,):
        return False
    return True


for path in paths:
    with open(path) as f:
        src = f.read()
    entries = yaml.safe_load(src).get("model_list", [])
    to_tag, kept = [], []
    for e in entries:
        name = e.get("model_name", "")
        target = (e.get("litellm_params") or {}).get("model", "")
        if (e.get("model_info") or {}).get("legacy_alias"):
            continue  # already tagged
        (to_tag if is_alias(name, target) else kept).append((name, target))
    print(f"== {path.split('/')[5]}")
    print(f"   keep : {[n for n, _ in kept]}")
    print(f"   alias: {[n for n, _ in to_tag]}")
    if not APPLY:
        continue
    lines = src.split("\n")
    out = []
    tag_names = {n for n, _ in to_tag}
    for line in lines:
        out.append(line)
        m = re.match(r"^(\s*)- model_name: (\S+)\s*$", line)
        if m and m.group(2) in tag_names:
            indent = m.group(1) + "  "
            out.append(f"{indent}model_info:")
            out.append(f"{indent}  legacy_alias: true")
    new_src = "\n".join(out)
    # sanity: still valid yaml, same entry count
    assert len(yaml.safe_load(new_src)["model_list"]) == len(entries)
    with open(path, "w") as f:
        f.write(new_src)
    print(f"   tagged {len(to_tag)} entries")
