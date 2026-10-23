#!/bin/bash
cd -- "$(dirname -- "$0")" || exit 1
if command -v python3.11 >/dev/null 2>&1; then
    python3.11 bootstrap.py "$@"
elif command -v python3 >/dev/null 2>&1; then
    python3 bootstrap.py "$@"
else
    echo '請先安裝 Python 3.11 以上版本，再重新啟動。'
    read -r -p '按 Enter 結束' _
    exit 1
fi
startup_status=$?
echo "Startup log: $(pwd)/startup.log"
read -r -p 'Press Enter to close this window. ' _
exit "$startup_status"
