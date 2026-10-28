"""Preflight checks for isolated B+C Windows research package (stdlib only)."""
import argparse
import json
from pathlib import Path
import sys

ESSENTIAL = ("START.bat", "START_BC_RESEARCH_TEST.bat", "bootstrap.py",
             "launch.py", "btc_app.py", "dashboard.py", "scanner.py",
             "agent_research_scheduler.py", "agent_single_instance.py",
             "agent_backup.py", "agent_restore.py", "requirements.txt",
             "agent_stage5_cycle.py", "agent_stage5_batch.py", "agent_stage5_review.py",
             "agent_stage5_ranking.py", "agent_stage6_delivery_gate.py",
             "agent_stage4_audit.py", "agent_stage_four_supervisor.py",
             "agent_stage_four_rotation.py", "agent_stage_four_checkpoint.py",
             "agent_stage_four_integrated_audit.py", "agent_stage_four_ui_status.py",
             "agent_stage_four_readiness.py", "agent_stage_four_research.py",
             "agent_forward_replay.py",
             "agent_forward_paper.py")
DANGEROUS = (".local-state", ".launcher-venv", ".agent-test-state", ".env", "startup.log",
             "scanner.log", "agent-research.log", "openai-stage4.log", "stage4-openai",
             ".env.local", ".env.production")


def inspect(root):
    root = Path(root).resolve()
    missing = [name for name in ESSENTIAL if not (root/name).is_file()]
    launcher = (root/"START_BC_RESEARCH_TEST.bat").read_text(encoding="utf-8") if not missing or (root/"START_BC_RESEARCH_TEST.bat").is_file() else ""
    isolated = 'BTC_NAVIGATOR_STATE_DIR=%~dp0.agent-test-state' in launcher and '--port 8591 --agent-research' in launcher
    included_runtime = [name for name in DANGEROUS if (root/name).exists()]
    return {"ready": not missing and isolated and not included_runtime,
            "missing_files":missing, "independent_start":isolated,
            "runtime_or_secret_paths":included_runtime}


def main():
    parser=argparse.ArgumentParser(description="B+C 研究版本發行檔案檢查")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent))
    args=parser.parse_args()
    report=inspect(args.root)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report["ready"] else 1


if __name__=="__main__":
    sys.exit(main())
