# -*- coding: utf-8 -*-
"""Threaded fetch layer over the bjbus MCP SSE endpoint, with disk cache + adaptive throttle."""
import io
import json
import os
import queue
import threading
import time

from q import call, _key
from mcp_client import McpSseClient

URL = "https://bjbus.jinzihao.me/sse"


class Limiter(object):
    """Shared token bucket.  Starts hopeful, halves the rate on any 503 and
    creeps back up while calls succeed."""

    def __init__(self, rate=6.0, floor=1.0, ceil=10.0):
        self.rate = rate
        self.floor = floor
        self.ceil = ceil
        self.lock = threading.Lock()
        self.next_t = time.time()

    def acquire(self):
        with self.lock:
            now = time.time()
            if self.next_t < now:
                self.next_t = now
            wait = self.next_t - now
            self.next_t += 1.0 / max(self.rate, 0.2)
        if wait > 0:
            time.sleep(wait)

    def slow_down(self):
        with self.lock:
            self.rate = max(self.floor, self.rate * 0.5)

    def speed_up(self):
        with self.lock:
            self.rate = min(self.ceil, self.rate * 1.05)


class Worker(threading.Thread):
    def __init__(self, jobs, results, name, limiter):
        threading.Thread.__init__(self, name=name)
        self.daemon = True
        self.jobs = jobs
        self.results = results
        self.limiter = limiter
        self.client = None
        self.connects = 0

    def _drop(self):
        try:
            if self.client:
                self.client.close()
        except Exception:
            pass
        self.client = None

    def run(self):
        while True:
            try:
                tool, args, key = self.jobs.get_nowait()
            except queue.Empty:
                return
            err = None
            try:
                if self.client is None:
                    self.client = McpSseClient(URL, timeout=90).start()
                    self.client.initialize()
                    self.connects += 1
                self.limiter.acquire()
                res = call(tool, args, use_cache=True, client=self.client)
                self.limiter.speed_up()
                self.results[key] = (res, None)
                self.jobs.task_done()
                continue
            except Exception as e:
                err = "%r" % (e,)
                if "503" in err or "Service Temporarily" in err:
                    self.limiter.slow_down()
                self._drop()
            self.results[key] = (None, err)
            self.jobs.task_done()


def fetch_many(tasks, nthreads=4, verbose=True, rounds=4, rate=None):
    """tasks: [(key, tool, args)] -> {key: (res, err)}; retries failures."""
    out = {}
    todo = []
    for key, tool, args in tasks:
        kp = _key(tool, args)
        if os.path.exists(kp):
            try:
                with io.open(kp, encoding="utf-8") as f:
                    out[key] = (json.load(f), None)
                continue
            except Exception:
                pass
        todo.append((tool, args, key))
    if verbose:
        print("[fetch] total=%d cached=%d to-fetch=%d" % (len(tasks), len(out), len(todo)), flush=True)
    if not todo:
        return out

    limiter = Limiter(rate=rate or 6.0)
    t0 = time.time()
    for rnd in range(rounds):
        if not todo:
            break
        jobs = queue.Queue()
        for t in todo:
            jobs.put(t)
        res = {}
        n = min(nthreads, len(todo))
        workers = [Worker(jobs, res, "w%d" % i, limiter) for i in range(n)]
        for w in workers:
            w.start()
        last = 0
        while any(w.is_alive() for w in workers):
            time.sleep(0.5)
            if verbose and len(res) - last >= 100:
                print("[fetch] r%d %d/%d %.0fs rate=%.1f/s"
                      % (rnd + 1, len(res), len(todo), time.time() - t0, limiter.rate), flush=True)
                last = len(res)
        out.update(res)
        failed = [(tool, args, key) for (tool, args, key) in todo if res.get(key, (None, "x"))[1]]
        todo = failed
        if verbose:
            print("[fetch] r%d ok=%d fail=%d rate=%.1f/s elapsed=%.0fs"
                  % (rnd + 1, len(res) - len(failed), len(failed), limiter.rate, time.time() - t0),
                  flush=True)
        if not failed:
            break
        time.sleep(2.0)
    if verbose:
        print("[fetch] done %.0fs have=%d still-bad=%d" % (time.time() - t0, len(out), len(todo)),
              flush=True)
    return out
