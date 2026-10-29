"""Restore a verified SQLite backup to a NEW, empty directory only.

Never replace a running BTC Navigator state database.
"""
from pathlib import Path
from contextlib import closing
import argparse
import json
import os
import sqlite3
import tempfile
from agent_backup import verify_backup, DATABASES


def restore_to_new_directory(backup_dir, new_state_dir):
    source = Path(backup_dir).resolve(strict=True)
    target = Path(new_state_dir).resolve()
    if target == source or source in target.parents or target in source.parents:
        raise ValueError("還原位置不可與備份目錄重疊")
    if target.exists():
        raise FileExistsError("還原目錄必須不存在，禁止覆蓋任何既有資料")
    verify_backup(source)
    manifest = json.loads((source / "backup-manifest.json").read_text(encoding="utf-8"))
    target.mkdir(parents=True, exist_ok=False)
    try:
        for item in manifest["files"]:
            name = item["file"]
            if name not in DATABASES:
                raise ValueError("未知的資料庫檔案")
            fd, temporary = tempfile.mkstemp(prefix=".restore-", suffix=".sqlite3", dir=target)
            os.close(fd)
            try:
                with closing(sqlite3.connect((source/name).as_uri()+"?mode=ro",uri=True)) as original:
                    with closing(sqlite3.connect(temporary)) as copied:
                        original.backup(copied)
                        if copied.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                            raise RuntimeError("資料庫還原檢查未通過")
                os.replace(temporary, target/name)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return {"restored": sorted(p.name for p in target.glob("*.sqlite3")),
                "location": str(target), "live_trading_authorized": False}
    except Exception:
        # Leave the partial folder for inspection rather than removing data unexpectedly.
        raise


def main():
    parser = argparse.ArgumentParser(description="將已驗證的研究備份還原到全新目錄")
    parser.add_argument("--backup", required=True)
    parser.add_argument("--new-state-dir", required=True)
    args = parser.parse_args()
    print(json.dumps(restore_to_new_directory(args.backup,args.new_state_dir),ensure_ascii=False))


if __name__ == "__main__":
    main()
