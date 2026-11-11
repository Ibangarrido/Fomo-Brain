"""Select the newest completed Clean V1 PAPER artifact by upload time.

GitHub run creation timestamps are not reliable artifact freshness indicators.
Fail closed rather than silently replaying an older ledger.
"""
import json
import math
import os
import sys
import urllib.request

NAME = "brain-clean-v1-state"
WORKFLOW = ".github/workflows/brain_clean_v1.yml"


def newest_artifact(items, current_run_id):
    eligible = [
        a for a in items
        if a.get("name") == NAME and not a.get("expired")
        and a.get("created_at")
        and (a.get("workflow_run") or {}).get("head_branch") == "main"
        and str((a.get("workflow_run") or {}).get("id")) != str(current_run_id)
    ]
    if not eligible:
        raise RuntimeError("No eligible Clean V1 PAPER artifact; refusing ledger reset")
    return max(eligible, key=lambda a: (a["created_at"], a["id"]))


def verify_ledger(state, report, run_id):
    previous = state.get("last_run") or {}
    reported = report.get("run") or {}
    if state.get("version") != 1 or str(previous.get("id")) != str(run_id):
        raise RuntimeError("Restored ledger provenance does not match selected run")
    if str(reported.get("id")) != str(run_id):
        raise RuntimeError("Restored report provenance does not match selected run")
    if not isinstance(state.get("positions"), dict) or not isinstance(state.get("closed"), list):
        raise RuntimeError("Incomplete PAPER ledger")
    if (not isinstance(state.get("cash"), (float, int)) or isinstance(state["cash"], bool)
            or not math.isfinite(state["cash"]) or state["cash"] < 0):
        raise RuntimeError("Invalid PAPER cash")


def api_json(path, repository, token):
    url = "https://api.github.com/repos/" + repository + path
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "CleanV1LedgerRestore/1.0",
    })
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)


def list_artifacts(repository, token):
    """Read every artifact page; never silently select from an incomplete list."""
    collected = []
    page = 1
    while True:
        payload = api_json(
            "/actions/artifacts?name=" + NAME + "&per_page=100&page=" + str(page),
            repository, token,
        )
        rows = payload.get("artifacts")
        total = payload.get("total_count")
        if not isinstance(rows, list) or not isinstance(total, int) or total < 0:
            raise RuntimeError("Incomplete artifact API response; refusing ledger reset")
        collected.extend(rows)
        if len(collected) >= total:
            return collected
        if not rows:
            raise RuntimeError("Artifact pagination stopped early; refusing ledger reset")
        page += 1


def select():
    repository = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    run_id = os.environ["GITHUB_RUN_ID"]
    artifacts = list_artifacts(repository, token)
    artifact = newest_artifact(artifacts, run_id)
    source_run = str(artifact["workflow_run"]["id"])
    run = api_json("/actions/runs/" + source_run, repository, token)
    path = str(run.get("path") or "").split("@")[0]
    if (run.get("status") != "completed" or run.get("conclusion") != "success"
            or not (path == WORKFLOW or path.endswith("/" + WORKFLOW))
            or run.get("head_branch") != "main"):
        raise RuntimeError("Selected artifact is not from a completed main Clean V1 run")
    print("CLEAN_RESTORE_SELECTED artifact=" + str(artifact["id"])
          + " source_run=" + source_run
          + " uploaded_at=" + artifact["created_at"], flush=True)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
        out.write("artifact_id=" + str(artifact["id"]) + "\n")
        out.write("source_run=" + source_run + "\n")


def verify():
    with open("brain_clean_v1_state.json", encoding="utf-8") as handle:
        state = json.load(handle)
    with open("brain_clean_v1_report.json", encoding="utf-8") as handle:
        report = json.load(handle)
    source_run = os.environ["CLEAN_RESTORE_SOURCE_RUN"]
    verify_ledger(state, report, source_run)
    print("CLEAN_RESTORE_VERIFIED source_run=" + source_run
          + " cash=" + str(state["cash"])
          + " positions=" + str(len(state["positions"]))
          + " closed=" + str(len(state["closed"])), flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("select", "verify"):
        raise SystemExit("Usage: clean_v1_restore.py select|verify")
    (select if sys.argv[1] == "select" else verify)()
