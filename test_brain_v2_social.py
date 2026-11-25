import unittest
from brain_v2_social import assess

class SocialTests(unittest.TestCase):
    def post(self,i,t,**kw):
        return dict(dict(mint="m",mint_verified=True,authorized_source=True,timestamp=t,source="public",post_id=str(i),author_id=str(i),text_fingerprint=str(i),is_repost=False,is_promoted=False),**kw)
    def sample(self):
        return [self.post(i,800) for i in range(3)]+[self.post(i,1800) for i in range(3,9)]
    def run_posts(self,p):
        return assess(p,mint="m",now=2000)
    def test_acceleration(self):
        self.assertEqual(self.run_posts(self.sample())["label"],"SOCIAL_ACCELERATION_WATCH")
    def test_duplicate(self):
        p=self.sample()
        self.assertEqual(self.run_posts(p+p)["recent_posts"],6)
    def test_repetition(self):
        p=self.sample()
        for row in p[3:]: row["text_fingerprint"]="same"
        self.assertEqual(self.run_posts(p)["label"],"REPETITIVE_CONTENT")
    def test_wrong_mint(self):
        self.assertEqual(self.run_posts([self.post(1,1800,mint="other")])["recent_posts"],0)
    def test_future(self):
        self.assertEqual(self.run_posts([self.post(1,2001)])["recent_posts"],0)
    def test_unverified(self):
        self.assertEqual(self.run_posts([self.post(1,1800,mint_verified=False)])["recent_posts"],0)
    def test_promoted(self):
        self.assertEqual(self.run_posts([self.post(1,1800,is_promoted=True)])["recent_posts"],0)
    def test_unauthorized(self):
        self.assertEqual(self.run_posts([self.post(1,1800,authorized_source=False)])["recent_posts"],0)
    def test_baseline(self):
        self.assertEqual(self.run_posts(self.sample()[3:])["label"],"INSUFFICIENT_BASELINE")
