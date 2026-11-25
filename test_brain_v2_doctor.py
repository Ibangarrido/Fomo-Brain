import unittest
from brain_v2_doctor import diagnose

class DoctorTests(unittest.TestCase):
    def run_case(self,**kw):
        return diagnose(**dict(dict(health={"issues":[]},artifact_verified=True,continuation_verified=True,source_status="OK",schedule_age_seconds=60),**kw))
    def test_healthy(self):
        self.assertTrue(self.run_case()["continuation_allowed"])
    def test_artifact(self):
        self.assertFalse(self.run_case(artifact_verified=False)["continuation_allowed"])
    def test_continuity(self):
        self.assertFalse(self.run_case(continuation_verified=None)["continuation_allowed"])
    def test_unknown_health(self):
        self.assertEqual(self.run_case(health=None)["incidents"][0]["code"],"HEALTH_UNKNOWN")
    def test_duplicate(self):
        self.assertEqual(len(self.run_case(health={"issues":["DUPLICATE","DUPLICATE"]})["incidents"]),1)
    def test_stale(self):
        self.assertEqual(self.run_case(schedule_age_seconds=3601)["incidents"][0]["code"],"SCHEDULE_STALE")
    def test_unknown_schedule(self):
        self.assertFalse(self.run_case(schedule_age_seconds=float("nan"))["continuation_allowed"])
    def test_retry(self):
        self.assertEqual(self.run_case(source_status="ERROR",retry_count=2)["retry_delay_seconds"],120)
    def test_escalation(self):
        r=self.run_case(source_status="ERROR",retry_count=3)
        self.assertIsNone(r["retry_delay_seconds"])
        self.assertEqual(r["mutations"],[])
        self.assertEqual(r["orders"],[])
