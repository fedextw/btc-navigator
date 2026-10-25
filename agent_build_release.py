"""Build a standalone source ZIP from reviewed tracked files only.

Never package local state, secrets, Git metadata, tests or temporary caches.
"""
from pathlib import Path
import argparse
import shutil
import subprocess
import tempfile
import zipfile
from agent_release_preflight import inspect

DENY_PARTS={".git",".github",".local-state",".agent-test-state",".launcher-venv",
            "__pycache__", "tests", "dist", "build", ".venv", ".pytest_cache"}
DENY_NAMES={".env","startup.log","agent-research.log","scanner.log"}
ALLOWED_SUFFIXES={".py",".bat",".txt",".json",".md",".toml",".yaml",".yml",".html",
                  ".css",".js",".svg",".png",".ico",".csv"}
PACKAGE_NAME="BTC_NAVIGATOR_BC_RESEARCH_TEST"


def build(root, output):
    root=Path(root).resolve()
    output=Path(output).resolve()
    if output == root or root in output.parents:
        # Permitted only for a dist folder: it must never be included.
        if output.parent != root/"dist":
            raise ValueError("輸出位置應為專用 dist 目錄或專案以外")
    tracked=subprocess.check_output(["git","ls-files","-z"],cwd=root).decode("utf-8").split("\0")
    approved=[]
    for relative in filter(None,tracked):
        file=Path(relative)
        if file.is_absolute() or ".." in file.parts or any(p in DENY_PARTS for p in file.parts):
            continue
        if file.name.lower() in DENY_NAMES or file.name.lower().startswith(".env"):
            continue
        if file.suffix.lower() not in ALLOWED_SUFFIXES:
            continue
        source=root/file
        if source.is_symlink():
            raise ValueError("發行檔案不可含符號連結")
        if source.is_file():
            approved.append(file)
    with tempfile.TemporaryDirectory() as tmp:
        stage=Path(tmp)/PACKAGE_NAME
        stage.mkdir()
        for relative in approved:
            target=stage/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(root/relative,target)
        result=inspect(stage)
        if not result["ready"]:
            raise RuntimeError(f"發行檢查失敗：{result}")
        output.parent.mkdir(parents=True,exist_ok=True)
        if output.exists():
            raise FileExistsError("輸出 ZIP 已存在，不覆蓋")
        with zipfile.ZipFile(output,"x",compression=zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(stage.rglob("*")):
                if file.is_file():
                    archive.write(file,file.relative_to(stage.parent).as_posix())
    return output


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",default=f"dist/{PACKAGE_NAME}.zip")
    args=parser.parse_args()
    print(build(Path(__file__).resolve().parent,args.out))


if __name__=="__main__":
    main()
