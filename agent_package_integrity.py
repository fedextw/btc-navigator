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
        # Python creates bytecode caches after the first launch; they were not
        # part of the ZIP and must not invalidate its immutable source files.
        actual={p.relative_to(root).as_posix() for p in root.rglob("*")
                if p.is_file() and p!=manifest and
                "__pycache__" not in p.relative_to(root).parts and
                ".agent-test-state" not in p.relative_to(root).parts}
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

def main():
    import argparse
    import sys
    parser=argparse.ArgumentParser(description="驗證解壓後的 B+C ZIP 核心檔案完整性")
    parser.add_argument("--root",default=str(Path(__file__).resolve().parent))
    args=parser.parse_args()
    passed=verify_package(args.root)
    if hasattr(sys.stdout,"reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("檔案完整性驗證通過" if passed else "檔案完整性驗證失敗：請重新取得原始 ZIP")
    return 0 if passed else 2

if __name__=="__main__":
    raise SystemExit(main())
