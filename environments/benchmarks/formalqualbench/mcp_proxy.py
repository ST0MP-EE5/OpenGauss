from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

COUNT_PATH_ENV = "GAUSS_AUTOFORMALIZE_MCP_COUNT_PATH"


def _increment_counter() -> None:
    count_path = str(os.getenv(COUNT_PATH_ENV, "") or "").strip()
    if not count_path:
        return
    path = Path(count_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    current = 0
    if path.exists():
        try:
            current = int(path.read_text(encoding="utf-8").strip() or "0")
        except Exception:
            current = 0
    path.write_text(f"{current + 1}\n", encoding="utf-8")


def _is_json_rpc_request(body: bytes) -> bool:
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return False
    if not isinstance(payload, dict):
        return False
    return isinstance(payload.get("method"), str)


def _pump(
    src,
    dst,
    *,
    count_requests: bool,
) -> None:
    buffer = bytearray()
    while True:
        chunk = src.read(4096)
        if not chunk:
            break
        buffer.extend(chunk)
        while True:
            header_end = buffer.find(b"\r\n\r\n")
            if header_end < 0:
                break
            header_block = bytes(buffer[:header_end]).decode("ascii", errors="ignore")
            match = re.search(r"Content-Length:\s*(\d+)", header_block, flags=re.IGNORECASE)
            if match is None:
                break
            content_length = int(match.group(1))
            frame_end = header_end + 4 + content_length
            if len(buffer) < frame_end:
                break
            frame = bytes(buffer[:frame_end])
            body = bytes(buffer[header_end + 4 : frame_end])
            if count_requests and _is_json_rpc_request(body):
                _increment_counter()
            dst.write(frame)
            dst.flush()
            del buffer[:frame_end]
    if buffer:
        dst.write(bytes(buffer))
        dst.flush()
    try:
        dst.close()
    except Exception:
        pass


def main(argv: list[str]) -> int:
    if not argv:
        print("Usage: mcp_proxy.py <command> [args...]", file=sys.stderr)
        return 2
    child = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
    )
    assert child.stdin is not None
    assert child.stdout is not None
    to_child = threading.Thread(
        target=_pump,
        args=(sys.stdin.buffer, child.stdin),
        kwargs={"count_requests": True},
        daemon=True,
    )
    from_child = threading.Thread(
        target=_pump,
        args=(child.stdout, sys.stdout.buffer),
        kwargs={"count_requests": False},
        daemon=True,
    )
    to_child.start()
    from_child.start()
    return child.wait()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
