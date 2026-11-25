"""PAPER ONLY incident triage. Plans recovery; never mutates state."""
import math

def diagnose(*, health, artifact_verified, continuation_verified, source_status,
             schedule_age_seconds, retry_count=0, max_schedule_age=3600):
    if type(retry_count) is not int or retry_count<0:
        raise ValueError("invalid retry count")
    incidents=[]
    def add(code,action,critical=True):
        incidents.append(dict(code=code,action=action,critical=critical))
    if artifact_verified is not True:
        add("ARTIFACT_UNVERIFIED","STOP_CONTINUATION_VERIFY_ARTIFACT")
    if continuation_verified is not True:
        add("CONTINUITY_UNVERIFIED","COMPARE_LEDGER_AND_SOURCE_RUN")
    if not isinstance(health,dict) or not isinstance(health.get("issues"),list):
        add("HEALTH_UNKNOWN","INSPECT_STATE_SCHEMA")
    else:
        for issue in sorted(set(str(x) for x in health["issues"])):
            add(issue,"INSPECT_STATE_READ_ONLY")
    if type(schedule_age_seconds) not in (int,float) or not math.isfinite(schedule_age_seconds) or schedule_age_seconds<0:
        add("SCHEDULE_UNKNOWN","VERIFY_SCHEDULE_RUN")
    elif schedule_age_seconds>max_schedule_age:
        add("SCHEDULE_STALE","INSPECT_WORKFLOW_TRIGGER")
    if source_status!="OK":
        add("SOURCE_UNAVAILABLE","RETRY_READ_ONLY_SOURCE" if retry_count<3 else "ESCALATE_SOURCE_FAILURE",False)
    return dict(scope="PAPER_ONLY_PLAN",incidents=incidents,
        continuation_allowed=not incidents,
        retry_delay_seconds=min(300,30*2**min(retry_count,4)) if source_status!="OK" and retry_count<3 else None,
        mutations=[],orders=[])
