"""Safe, opt-in offline backup of BTC Navigator research SQLite data.

Uses SQLite's online backup API to read a consistent snapshot. Never copies
secrets, passwords, configuration, or mutable database files using shutil.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import os

DATABASES = ("research.sqlite3", "signals.sqlite3")
MAX_BACKUP_BYTES = 2_000_000_000


def backup_state(state_dir, destination):
    state = Path(state_dir).resolve()
    destination = Path(destination).resolve()
    if not state.is_dir():
        raise ValueError("狀態資料夾不存在")
    if destination == state or state in destination.parents:
        raise ValueError("備份目錄不可位於正在運作的狀態資料夾內")
    destination.mkdir(parents=True, exist_ok=True)
    manifest = {"schema":"btc-backup-v1", "created_utc":datetime.now(timezone.utc).isoformat(),
                "source":"offline-sqlite-snapshot", "files":[]}
    for name in DATABASES:
        source = state / name
        if not source.is_file():
            continue
        if source.stat().st_size > MAX_BACKUP_BYTES:
            raise ValueError("資料庫超過備份限制")
        target = destination / name
        if target.exists():
            raise FileExistsError("備份目的地已有相同檔案，拒絕覆蓋")
        fd, temp_name = tempfile.mkstemp(prefix=".backup-", suffix=".sqlite3", dir=destination)
        os.close(fd)
        try:
            # Read-only URI ensures the source never receives write operations.
            uri = source.resolve().as_uri() + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True, timeout=10)) as src:
                with closing(sqlite3.connect(temp_name)) as dst:
                    src.backup(dst)
                    check = dst.execute("PRAGMA integrity_check").fetchone()[0]
                    if check != "ok":
                        raise RuntimeError("SQLite 備份完整性檢查失敗")
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        manifest["files"].append({"file":name,"sha256":hashlib.sha256(target.read_bytes()).hexdigest(),
                                  "bytes":target.stat().st_size})
    if not manifest["files"]:
        raise ValueError("找不到可備份的研究資料庫")
    manifest_path = destination / "backup-manifest.json"
    with manifest_path.open("x",encoding="utf-8") as handle:
        json.dump(manifest,handle,ensure_ascii=False,indent=2)
    return manifest


def verify_backup(destination):
    destination=Path(destination).resolve()
    report=json.loads((destination/"backup-manifest.json").read_text(encoding="utf-8"))
    if report.get("schema") != "btc-backup-v1" or not isinstance(report.get("files"),list) or not report["files"]:
        raise ValueError("不認得的備份清單")
    for item in report["files"]:
        if item.get("file") not in DATABASES:
            raise ValueError("備份檔案名稱不合法")
        path=destination/item["file"]
        if hashlib.sha256(path.read_bytes()).hexdigest()!=item["sha256"]:
            raise ValueError("備份校驗碼不一致")
        with closing(sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True)) as conn:
            if conn.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                raise ValueError("備份資料庫完整性錯誤")
    return True


def main():
    p=argparse.ArgumentParser(description="BTC Navigator SQLite 資料安全快照備份")
    p.add_argument("--state-dir",default=".local-state")
    p.add_argument("--out",required=True)
    args=p.parse_args()
    result=backup_state(args.state_dir,args.out)
    verify_backup(args.out)
    print(json.dumps({"verified":True,"files":result["files"]},ensure_ascii=False))


if __name__=="__main__":
    main()
