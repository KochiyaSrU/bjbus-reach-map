# -*- coding: utf-8 -*-
"""Minimal MCP SSE client (protocol 2024-11-05) using only stdlib."""
import json
import queue
import threading
import http.client
import ssl
from urllib.parse import urlparse, urljoin


class McpSseClient(object):
    def __init__(self, url, timeout=30):
        self.url = url
        self.timeout = timeout
        u = urlparse(url)
        self.host = u.hostname
        self.port = u.port or (443 if u.scheme == "https" else 80)
        self.scheme = u.scheme
        self.path = u.path or "/"
        self.q = queue.Queue()
        self.endpoint = None
        self.ready = threading.Event()
        self._id = 0
        self._lock = threading.Lock()
        self.log = []

    # ---------- transport ----------
    def _connect(self):
        if self.scheme == "https":
            ctx = ssl.create_default_context()
            self.conn = http.client.HTTPSConnection(self.host, self.port, timeout=None, context=ctx)
        else:
            self.conn = http.client.HTTPConnection(self.host, self.port, timeout=None)
        self.conn.request("GET", self.path, headers={
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
        })
        self.resp = self.conn.getresponse()
        if self.resp.status != 200:
            raise RuntimeError("SSE GET failed: %s" % self.resp.status)

    def _read_loop(self):
        try:
            event = None
            data_lines = []
            while True:
                raw = self.resp.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                if line == "":
                    if event == "endpoint" and data_lines:
                        ep = "".join(data_lines).strip()
                        self.endpoint = ep
                        self.ready.set()
                    elif event == "message" and data_lines:
                        try:
                            self.q.put(json.loads("".join(data_lines)))
                        except Exception as e:
                            self.log.append("bad json: %s" % e)
                    event = None
                    data_lines = []
                    continue
                if line.startswith(":"):
                    continue
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[5:].strip())
        except Exception as e:
            self.log.append("read_loop err: %r" % (e,))
        finally:
            self.ready.set()
            self.q.put(None)

    def start(self):
        self._connect()
        t = threading.Thread(target=self._read_loop, name="sse-reader")
        t.daemon = True
        t.start()
        if not self.ready.wait(self.timeout):
            raise RuntimeError("no endpoint event within timeout")
        if not self.endpoint:
            raise RuntimeError("endpoint not received")
        return self

    def _post(self, payload):
        u = urlparse(urljoin(self.url, self.endpoint))
        path = u.path + (("?" + u.query) if u.query else "")
        body = json.dumps(payload).encode("utf-8")
        if self.scheme == "https":
            ctx = ssl.create_default_context()
            c = http.client.HTTPSConnection(u.hostname, u.port or 443, timeout=self.timeout, context=ctx)
        else:
            c = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=self.timeout)
        c.request("POST", path, body=body, headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        })
        r = c.getresponse()
        raw = r.read()
        c.close()
        return r.status, raw

    # ---------- jsonrpc ----------
    def _call(self, method, params=None, notify=False):
        with self._lock:
            if notify:
                self._post({"jsonrpc": "2.0", "method": method})
                return None
            self._id += 1
            mid = self._id
        payload = {"jsonrpc": "2.0", "id": mid, "method": method}
        if params is not None:
            payload["params"] = params
        status, raw = self._post(payload)
        if status not in (200, 202, 204):
            raise RuntimeError("POST %s -> %s %r" % (method, status, raw[:300]))
        # wait for matching response on the SSE stream
        while True:
            try:
                msg = self.q.get(timeout=self.timeout)
            except queue.Empty:
                raise RuntimeError("timeout waiting response for %s (id=%s)" % (method, mid))
            if msg is None:
                raise RuntimeError("stream closed while waiting for %s; log=%s" % (method, self.log))
            if isinstance(msg, dict) and msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError("rpc error: %s" % json.dumps(msg["error"], ensure_ascii=False))
                return msg.get("result")

    def initialize(self):
        res = self._call("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "dsh-bjbus", "version": "0.1.0"},
        })
        self._call("notifications/initialized", notify=True)
        return res

    def list_tools(self):
        return self._call("tools/list", {})

    def call_tool(self, name, args):
        return self._call("tools/call", {"name": name, "arguments": args})

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    import sys
    c = McpSseClient("https://bjbus.jinzihao.me/sse").start()
    info = c.initialize()
    print("SERVER:", json.dumps(info, ensure_ascii=False)[:600])
    tools = c.list_tools()
    for t in tools.get("tools", []):
        print("=" * 70)
        print("TOOL:", t.get("name"))
        print("DESC:", (t.get("description") or "")[:800])
        print("SCHEMA:", json.dumps(t.get("inputSchema"), ensure_ascii=False)[:1200])
    c.close()
