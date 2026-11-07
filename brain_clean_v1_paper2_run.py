"""Run the existing Clean V1 engine against PAPER2 only; never bootstrap on a run."""
import json
import os
import brain_clean_v1 as brain
import brain_clean_v1_paper2 as paper2

REPORT_FILE = "brain_clean_v1_paper2_report.json"

def verify_run_identity(source_run, current_run):
    """Never replay an already persisted PAPER2 run or accept absent run IDs."""
    if not source_run or not current_run:
        raise RuntimeError("Missing PAPER2 source/current run ID")
    if str(source_run) == str(current_run):
        raise RuntimeError("PAPER2 replay detected: source and current run are identical")


def run():
    state = paper2.load_existing()
    previous = state.get("last_run")
    expected = os.environ.get("PAPER2_SOURCE_RUN")
    verify_run_identity(expected, os.environ.get("GITHUB_RUN_ID"))
    if previous:
        if str(previous.get("id")) != expected:
            raise RuntimeError("PAPER2 restored run provenance mismatch")
    elif (expected != os.environ.get("PAPER2_BOOTSTRAP_RUN")
          or os.environ.get("PAPER2_SOURCE_WORKFLOW") != "brain_clean_v1_paper2_bootstrap.yml"):
        raise RuntimeError("Unverified PAPER2 bootstrap provenance")
    brain.STATE_FILE = paper2.STATE_FILE
    brain.REPORT_FILE = REPORT_FILE
    brain.load_state = lambda path=None: paper2.load_existing()
    brain.main()
    with open(REPORT_FILE, encoding="utf-8") as handle:
        report = json.load(handle)
    if report.get("run", {}).get("id") != os.environ.get("GITHUB_RUN_ID"):
        raise RuntimeError("PAPER2 report run provenance mismatch")
    if paper2.load_existing().get("last_run", {}).get("id") != os.environ.get("GITHUB_RUN_ID"):
        raise RuntimeError("PAPER2 state run provenance mismatch")

if __name__ == "__main__":
    run()
