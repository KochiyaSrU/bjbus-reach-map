# -*- coding: utf-8 -*-
"""Query helper: q.py <tool_name> <json_args>  -> prints compact JSON, caches to cache/."""
import json
import os
import sys
import hashlib
from mcp_client import McpSseClient

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
if not os.path.isdir(CACHE):
    os.makedirs(CACHE)


def _key(tool, args):
    h = hashlib.md5((tool + "|" + json.dumps(args, sort_keys=True, ensure_ascii=False)).encode("utf-8")).hexdigest()
    return os.path.join(CACHE, "%s_%s.json" % (tool, h[:10]))


def call(tool, args, use_cache=True, client=None):
    kp = _key(tool, args)
    if use_cache and os.path.exists(kp):
        with open(kp, "r", encoding="utf-8") as f:
            return json.load(f)
    own = client is None
    if own:
        client = McpSseClient("https://bjbus.jinzihao.me/sse").start()
        client.initialize()
    try:
        res = client.call_tool(tool, args)
    finally:
        if own:
            client.close()
    # result comes as {content:[{type:text,text:...}], isError?}
    out = res
    if isinstance(res, dict) and "content" in res:
        texts = [c.get("text", "") for c in res["content"] if c.get("type") == "text"]
        joined = "\n".join(texts)
        try:
            out = json.loads(joined)
        except Exception:
            out = {"_raw_text": joined, "_isError": res.get("isError")}
    with open(kp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    return out


if __name__ == "__main__":
    tool = sys.argv[1]
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    r = call(tool, args)
    s = json.dumps(r, ensure_ascii=False, indent=1)
    print(s[:6000])
    print("...len=%d" % len(s))
