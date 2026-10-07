from datetime import datetime, timezone
import unittest
from unittest.mock import Mock
from social_radar import collect_posts

NOW = datetime(2026, 10, 7, 4, 30, tzinfo=timezone.utc)


def payload(account="elonmusk", post_id="123", text="A funny frog"):
    return {"data": [{"id": post_id, "author_id": "42", "created_at": NOW.isoformat(),
                      "text": text}], "includes": {"users": [{"id": "42", "username": account}]}}


class SocialTests(unittest.TestCase):
    def test_both_accounts_without_keyword_filter(self):
        fetch = Mock(side_effect=[payload("realDonaldTrump", "123"), payload("elonmusk", "124")])
        events, status, coverage = collect_posts(fetch, ["realDonaldTrump", "elonmusk"], ["crypto"], NOW)
        self.assertEqual(status, "CONSULTA OK")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[1]["keywords"], [])
        self.assertEqual(events[1]["url"], "https://x.com/elonmusk/status/124")
        self.assertEqual(fetch.call_args_list[1].args[0]["query"], "from:elonmusk -is:retweet")

    def test_wrong_author_missing_identity_or_date_rejected(self):
        for mutate in (lambda p: p["includes"]["users"][0].update(username="imposter"),
                       lambda p: p.pop("includes"),
                       lambda p: p["data"][0].update(created_at="2025-01-01T00:00:00Z"),
                       lambda p: p["data"][0].update(created_at="bad")):
            p = payload()
            mutate(p)
            events, status, coverage = collect_posts(lambda _: p, ["elonmusk"], [], NOW)
            self.assertEqual(events, [])
            self.assertNotEqual(status, "CONSULTA OK")

    def test_account_error_does_not_hide_other_account(self):
        fetch = Mock(side_effect=[OSError("no access"), payload()])
        events, status, coverage = collect_posts(fetch, ["realDonaldTrump", "elonmusk"], [], NOW)
        self.assertEqual(len(events), 1)
        self.assertEqual(coverage["realDonaldTrump"]["status"], "ERROR")
        self.assertNotEqual(status, "CONSULTA OK")

    def test_pagination_and_deduplication(self):
        first = payload()
        first["meta"] = {"next_token": "next"}
        fetch = Mock(side_effect=[first, payload()])
        events, status, coverage = collect_posts(fetch, ["elonmusk"], [], NOW)
        self.assertEqual(len(events), 1)
        self.assertEqual(fetch.call_args.args[0]["next_token"], "next")
        self.assertTrue(coverage["elonmusk"]["complete"])

    def test_page_limit_is_not_complete(self):
        p = payload()
        p["meta"] = {"next_token": "more"}
        events, status, coverage = collect_posts(lambda _: p, ["elonmusk"], [], NOW)
        self.assertEqual(coverage["elonmusk"]["pages"], 3)
        self.assertFalse(coverage["elonmusk"]["complete"])

    def test_no_posts_is_success_not_a_signal(self):
        events, status, coverage = collect_posts(lambda _: {"meta": {"result_count": 0}}, ["elonmusk"], [], NOW)
        self.assertEqual(events, [])
        self.assertEqual(status, "CONSULTA OK")

    def test_retweets_rejected(self):
        p = payload()
        p["data"][0]["referenced_tweets"] = [{"type": "retweeted", "id": "1"}]
        self.assertEqual(collect_posts(lambda _: p, ["elonmusk"], [], NOW)[0], [])


if __name__ == "__main__":
    unittest.main()
