"""Verify extracted B+C release content against its build-time SHA-256 manifest."""
import hashlib
import json
from pathlib import Path

def verify_package(root):
    root=Path(root)
    manifest=root/"PACKAGE_SHA256.json"
    if not manifest.is_file() or manifest.stat().st_size>1000000:
        return False
    try:
        payload=json.loads(manifest.read_text(encoding="utf-8"))
        files=payload["files"]
        if payload.get("schema")!="agent-package-sha256-v1" or not isinstance(files,dict) or not files:
            return False
        actual={p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and p!=manifest}
        if set(files)!=actual:
            return False
        for relative,expected in files.items():
            p=Path(relative)
            if (p.is_absolute() or ".." in p.parts or p.as_posix()!=relative or
                not isinstance(expected,str) or len(expected)!=64 or
                hashlib.sha256((root/p).read_bytes()).hexdigest()!=expected):
                return False
        return True
    except (ValueError,TypeError,KeyError,OSError):
        return False
