# -*- coding: utf-8 -*-
"""Gentle sequential backfill: one request at a time, 1.2 s apart, 503 backoff."""
import io
import json
import os
import sys
import time

from q import call, _key
from mcp_client import McpSseClient

URL = "https://bjbus.jinzihao.me/sse"
GAP = 1.2


def need_list():
    stage = json.load(io.open("out_leg2_stage_a.json", encoding="utf-8"))
    leg1 = json.load(io.open("out_leg1.json", encoding="utf-8"))["leg1"]
    ids = sorted(set(stage["need_routes"]) | set(x["route_id"] for x in leg1))
    tasks = []
    for rid in ids:
        for tool, args in (("query_route_info_by_route_id", {"route_id": rid}),
                           ("query_route_timetable", {"route_id": rid})):
            if not os.path.exists(_key(tool, args)):
                tasks.append((tool, args))
    return tasks


def main():
    tasks = need_list()
    print("missing:", len(tasks), flush=True)
    if not tasks:
        return
    client = McpSseClient(URL, timeout=90).start()
    client.initialize()
    ok = fail = 0
    t0 = time.time()
    for i, (tool, args) in enumerate(tasks):
        done = False
        for attempt in range(4):
            try:
                call(tool, args, use_cache=True, client=client)
                ok += 1
                done = True
                break
            except Exception as e:
                wait = [6, 20, 60, 150][attempt]
                print("  retry %s %s in %ss (%s)" % (tool, args, wait, repr(e)[:60]), flush=True)
                try:
                    client.close()
                except Exception:
                    pass
                time.sleep(wait)
                try:
                    client = McpSseClient(URL, timeout=90).start()
                    client.initialize()
                except Exception as e2:
                    print("  reconnect failed", repr(e2)[:60], flush=True)
        if not done:
            fail += 1
        time.sleep(GAP)
        if (i + 1) % 25 == 0:
            print("  %d/%d ok=%d fail=%d  %.0fs" % (i + 1, len(tasks), ok, fail, time.time() - t0), flush=True)
    print("done ok=%d fail=%d in %.0fs" % (ok, fail, time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
