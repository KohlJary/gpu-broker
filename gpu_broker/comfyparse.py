"""ComfyUI's wire formats, as pure functions: the multipart body of an input upload, and the
outputs of a finished prompt in its /history entry. No HTTP here; backends.py sends and fetches."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NamedTuple

from .constants import ERR_DETAIL

UPLOAD_FIELDS = {"type": "input", "overwrite": "true"}   # into ComfyUI's input folder, as named
OUTPUT_KINDS = ("images", "videos", "gifs", "audio")
EXECUTION_ERROR = "execution_error"
STATUS_ERROR = "error"


class Output(NamedTuple):
    filename: str
    subfolder: str
    kind: str | None   # ComfyUI's own `type` (output or temp), when it gives one


def upload_body(boundary: str, name: str, data: bytes, mime: str) -> bytes:
    """A multipart/form-data body for ComfyUI's /upload/image: the fixed fields, then the image."""
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
             for k, v in UPLOAD_FIELDS.items()]
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\n'
                 f"Content-Type: {mime}\r\n\r\n".encode() + data + b"\r\n")
    return b"".join(parts) + f"--{boundary}--\r\n".encode()


def finished(entry: Mapping[str, Any]) -> list[Output] | None:
    """A prompt's output files once it completed, None while it runs; raises on an execution error."""
    status = entry["status"]
    if status.get("status_str") == STATUS_ERROR:
        msgs = [m[1].get("exception_message", "") for m in status.get("messages", []) if m[0] == EXECUTION_ERROR]
        raise RuntimeError(f"ComfyUI execution error: {(msgs or ['unknown'])[0][:ERR_DETAIL]}")
    if not status.get("completed"):
        return None
    return [Output(f["filename"], f.get("subfolder", ""), f.get("type"))
            for node in entry["outputs"].values() for kind in OUTPUT_KINDS for f in node.get(kind, [])]

