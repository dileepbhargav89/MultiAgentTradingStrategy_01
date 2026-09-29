"""Comprehensive Regression Test Runner: Executes all 12 Sprint Verification Suites."""

import subprocess
import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCRIPTS = [
    ("Sprint 1: Data Quality & Ingestion", "scripts/verify_sprint1.py"),
    ("Sprint 2: Technical Confluence", "scripts/verify_sprint2.py"),
    ("Sprint 3: Market Intelligence & Crowding", "scripts/verify_sprint3.py"),
    ("Sprint 4: Volatility & Regime Forecasting", "scripts/verify_sprint4.py"),
    ("Sprint 5: Strategy Evolution Foundation", "scripts/verify_sprint5.py"),
    ("Sprint 6: GA Engine & Walk-Forward Validation", "scripts/verify_sprint6.py"),
    ("Sprint 7: Risk Management & Cornish-Fisher VaR", "scripts/verify_sprint7.py"),
    ("Sprint 8: Money Management & Trade Decider", "scripts/verify_sprint8.py"),
    ("Sprint 9: Trade Execution & Bracket Engine", "scripts/verify_sprint9.py"),
    ("Sprint 10: Master Orchestrator & State Recovery", "scripts/verify_sprint10.py"),
    ("Sprint 11: Dashboard, WebSocket & Operator Overrides", "scripts/verify_sprint11.py"),
    ("Sprint 12: Committee Backtester & Tear-Sheet", "scripts/verify_sprint12.py"),
]


def run_all() -> int:
    print("=" * 80)
    print("🔬 STRATEGYONE: COMPREHENSIVE MULTI-AGENT REGRESSION TEST RUNNER")
    print("=" * 80)
    print(f"Running all {len(SCRIPTS)} Sprint Verification Suites sequentially...\n")

    results = []
    total_start = time.perf_counter()

    for idx, (title, script_path) in enumerate(SCRIPTS, start=1):
        print(f"[{idx}/{len(SCRIPTS)}] Running {title} ({script_path})...", end=" ", flush=True)
        start_t = time.perf_counter()

        proc = subprocess.run(
            [sys.executable, script_path],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        elapsed = time.perf_counter() - start_t

        if proc.returncode == 0:
            print(f"✅ PASSED ({elapsed:.2f}s)")
            results.append((title, "PASS", elapsed, ""))
        else:
            print(f"❌ FAILED ({elapsed:.2f}s)")
            err_snip = proc.stderr[-500:] if proc.stderr else proc.stdout[-500:]
            results.append((title, "FAIL", elapsed, err_snip))

    total_time = time.perf_counter() - total_start

    print("\n" + "=" * 80)
    print("📋 REGRESSION TEST RESULTS SUMMARY")
    print("=" * 80)
    print(f"{'Sprint Suite':<48} | {'Status':<8} | {'Duration'}")
    print("-" * 80)

    all_passed = True
    for title, status, elapsed, err in results:
        status_icon = "✅ PASS" if status == "PASS" else "❌ FAIL"
        if status != "PASS":
            all_passed = False
        print(f"{title:<48} | {status_icon:<8} | {elapsed:.2f}s")
        if err:
            print(f"   --> Error Details: {err.strip()}\n")

    print("-" * 80)
    print(f"Total Execution Time: {total_time:.2f}s")
    if all_passed:
        print("🎉 ALL 12 SPRINT SUITES PASSED! ZERO REGRESSIONS DETECTED.")
        print("=" * 80)
        return 0
    else:
        print("⚠️ SOME REGRESSION TESTS FAILED. PLEASE REVIEW LOGS ABOVE.")
        print("=" * 80)
        return 1


if __name__ == "__main__":
    sys.exit(run_all())
