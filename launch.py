"""One-command local launcher. Uses normal TLS verification for package downloads."""
import argparse
import hashlib
import os
from pathlib import Path
import socket
import signal
import subprocess
import sys
import time
import urllib.request
import venv
import webbrowser

ROOT = Path(__file__).resolve().parent


def handle_termination(_signum, _frame):
    raise KeyboardInterrupt


def stop(process):
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main():
    # Prevent Windows redirected-console cp1252 encoding failures on Chinese status text.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="backslashreplace")
    signal.signal(signal.SIGTERM, handle_termination)
    parser = argparse.ArgumentParser(description="BTC Navigator 一鍵啟動：網站＋背景研究（無自動下單）")
    parser.add_argument("--demo", action="store_true", help="合成行情模式，不對外收集資料")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--symbol", default="BTCUSDT", help="單幣研究預設顯示的 USDT 交易對；不限制全市場掃描")
    parser.add_argument("--interval", choices=["15m", "1h", "4h"], default="1h")
    parser.add_argument("--check", action="store_true", help="安裝並檢查相依套件後結束")
    parser.add_argument("--agent-research", action="store_true", help="額外啟用獨立紙上策略研究排程（試驗功能，預設關閉）")
    parser.add_argument("--ready", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--demo-test-stop", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        raise SystemExit("請先安裝 Python 3.11 以上版本，再重新啟動。")
    if args.demo_test_stop and not args.demo:
        parser.error("測試停止標記只能搭配 --demo")
    if not 1024 <= args.port <= 65535:
        parser.error("port 必須介於 1024 與 65535")
    os.chdir(ROOT)
    if not args.ready:
        env_dir = ROOT / ".launcher-venv"
        python = env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not python.exists():
            print("[1/3] 建立獨立 Python 環境…", flush=True)
            venv.EnvBuilder(with_pip=True).create(env_dir)
        requirements = ROOT / "requirements-lock.txt"
        if not requirements.exists():
            requirements = ROOT / "requirements.txt"
        digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
        marker = env_dir / "requirements.sha256"
        if not marker.exists() or marker.read_text() != digest:
            print("[2/3] 安裝套件（第一次可能需要幾分鐘）…", flush=True)
            subprocess.run([str(python), "-m", "pip", "install", "-r", str(requirements)], check=True)
            subprocess.run([str(python), "-m", "pip", "check"], check=True)
            marker.write_text(digest)
        child = subprocess.Popen([str(python), str(Path(__file__).resolve()), "--ready", *sys.argv[1:]])
        try:
            return child.wait()
        except KeyboardInterrupt:
            stop(child)
            return 0
    if args.check:
        subprocess.run([sys.executable, "-m", "pip", "check"], check=True)
        from market_data import demo_market
        from analysis_engine import analyze
        assert analyze(demo_market("BTCUSDT", "1h"))["valid"]
        print("環境檢查通過。", flush=True)
        return 0
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", args.port)) == 0:
            raise SystemExit(f"連接埠 {args.port} 已被使用。請關閉先前視窗，或使用 --port 指定其他連接埠。")
    state = Path(os.environ.get("BTC_NAVIGATOR_STATE_DIR", str(ROOT / ".local-state")))
    state.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["BTC_NAVIGATOR_STATE_DIR"] = str(state.resolve())
    environment["BTC_DEFAULT_SYMBOL"] = args.symbol
    environment["BTC_DEFAULT_INTERVAL"] = args.interval
    if args.demo:
        environment["BTC_NAVIGATOR_DEMO"] = "1"
    ui = worker = agent = None
    worker_log = agent_log = None
    try:
        print("[3/3] 啟動網站與持續研究程序…", flush=True)
        ui = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "btc_app.py",
            "--server.address=127.0.0.1", f"--server.port={args.port}", "--server.headless=true",
            "--browser.gatherUsageStats=false"], cwd=ROOT, env=environment)
        ready = False
        for _ in range(80):
            if ui.poll() is not None:
                raise RuntimeError("網站程序提前結束，請查看上方錯誤。")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{args.port}/_stcore/health", timeout=1) as response:
                    ready = response.status == 200
            except OSError:
                pass
            if ready:
                break
            time.sleep(.5)
        if not ready:
            raise RuntimeError("網站未在 40 秒內就緒。")
        from monitor_settings import load_settings, save_settings
        if not (state / "monitor-settings.json").exists():
            save_settings({"interval": args.interval}, state)
        worker_log = (state / "scanner.log").open("a", encoding="utf-8")
        command = [sys.executable, "scanner.py"]
        if args.demo:
            command.append("--demo")
        worker = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=worker_log, stderr=subprocess.STDOUT)
        if args.agent_research:
            # Separate process; its exit never stops the scanner or website.
            # Bound to the chosen symbol, once per 24h; no trading permissions.
            from agent_symbol_validation import valid_symbol
            if not valid_symbol(args.symbol):
                raise ValueError("Agent 研究幣種格式不正確")
            agent_log = (state / "agent-research.log").open("a", encoding="utf-8")
            agent_command = [sys.executable, "agent_research_scheduler.py",
                             "--state-dir", str(state.resolve()),
                             "--symbols", args.symbol, "--interval", args.interval,
                             "--mode", "demo" if args.demo else "live", "--hours", "24",
                             "--proposal-research"]
            try:
                agent = subprocess.Popen(agent_command, cwd=ROOT, env=environment,
                                         stdout=agent_log, stderr=subprocess.STDOUT)
                print("獨立 Agent 研究程序已啟用（僅紙上研究）。", flush=True)
            except OSError as exc:
                print(f"Agent 研究未啟動：{type(exc).__name__}；行情掃描不受影響。", flush=True)

        print("網站已啟動。背景會動態掃描全 Binance USDT 永續合約，設定與 Telegram 推播請到「全市場訊號」。", flush=True)
        print("保留此視窗即可持續運作；關閉瀏覽器不會停止。按 Ctrl+C 停止網站與背景程序。", flush=True)
        print("這是研究與紙上模擬系統，沒有自動下單功能。", flush=True)
        if not args.no_browser:
            webbrowser.open(f"http://127.0.0.1:{args.port}")
        agent_restart_count = 0
        agent_next_restart = None
        while ui.poll() is None:
            # Test-only cooperative exit on Windows, where Popen.terminate does
            # not notify this parent process and can orphan its descendants.
            if args.demo_test_stop and (state / ".demo-test-stop").exists():
                print("收到示範整合測試停止指令，正在正常關閉子程序。", flush=True)
                break
            if agent and agent.poll() is not None:
                print("Agent 研究程序已停止；主網站與行情掃描不受影響。", flush=True)
                agent = None
                if agent_restart_count < 2:
                    agent_next_restart = time.monotonic() + 60
                else:
                    print("Agent 已達最多兩次重啟上限，請查閱 agent-research.log。", flush=True)
            if agent is None and agent_next_restart is not None and time.monotonic() >= agent_next_restart:
                agent_next_restart = None
                agent_restart_count += 1
                try:
                    agent = subprocess.Popen(agent_command, cwd=ROOT, env=environment,
                                             stdout=agent_log, stderr=subprocess.STDOUT)
                    print(f"Agent 研究已重啟（{agent_restart_count}/2）。", flush=True)
                except OSError as exc:
                    print(f"Agent 重啟失敗：{type(exc).__name__}；不影響行情。", flush=True)
                    if agent_restart_count < 2:
                        agent_next_restart = time.monotonic() + 60
            if worker.poll() is not None:
                raise RuntimeError("背景研究程序已停止。請查看 .local-state/scanner.log。")
            time.sleep(1)
        return ui.returncode
    except KeyboardInterrupt:
        print("\n停止研究程序，紀錄已保留。", flush=True)
        return 0
    finally:
        stop(agent)
        stop(worker)
        stop(ui)
        if agent_log:
            agent_log.close()
        if worker_log:
            worker_log.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"啟動失敗：{exc}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(0)
