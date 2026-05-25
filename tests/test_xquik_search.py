import os
import unittest
from unittest.mock import patch

from opentwitter_mcp.xquik_search import (
    _auth_headers,
    _build_search_query,
    _build_search_url,
    _resolve_api_key,
    normalize_search_payload,
    resolve_search_backend,
)


class XquikSearchTest(unittest.TestCase):
    def test_resolves_only_xquik_backend(self) -> None:
        self.assertEqual(resolve_search_backend("xquik"), "xquik")
        self.assertEqual(resolve_search_backend(" XQUIK "), "xquik")
        self.assertEqual(resolve_search_backend("default"), "default")
        with patch.dict(os.environ, {"TWITTER_SEARCH_BACKEND": "xquik"}, clear=True):
            self.assertEqual(resolve_search_backend(), "xquik")

    def test_api_key_uses_xquik_env_only(self) -> None:
        with patch.dict(os.environ, {"XQUIK_API_KEY": "  xq_test  "}, clear=True):
            self.assertEqual(_resolve_api_key(), "xq_test")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "Xquik search requires XQUIK_API_KEY"):
                _resolve_api_key()

    def test_auth_headers_match_key_kind(self) -> None:
        self.assertEqual(
            _auth_headers("xq_abc"),
            {"x-api-key": "xq_abc", "Accept": "application/json"},
        )
        self.assertEqual(
            _auth_headers("plain"),
            {"Authorization": "Bearer plain", "Accept": "application/json"},
        )
        self.assertEqual(
            _auth_headers("Bearer token"),
            {"Authorization": "Bearer token", "Accept": "application/json"},
        )

    def test_builds_query_and_url(self) -> None:
        query = _build_search_query(
            keywords="bitcoin",
            from_user="@alice",
            to_user="bob",
            mention_user="@carol",
            hashtag="#crypto",
            exclude_replies=True,
            exclude_retweets=True,
            min_likes=10,
            min_retweets=3,
            min_replies=2,
            lang="en",
        )
        self.assertIn("bitcoin", query)
        self.assertIn("from:alice", query)
        self.assertIn("to:bob", query)
        self.assertIn("@carol", query)
        self.assertIn("#crypto", query)
        self.assertIn("-filter:replies", query)
        self.assertIn("min_faves:10", query)

        with patch.dict(os.environ, {"XQUIK_BASE_URL": "https://example.test/"}, clear=True):
            url = _build_search_url(
                query=query,
                since_date="2026-01-01",
                until_date="2026-01-02",
                product="Latest",
                max_results=500,
            )
        self.assertIn("https://example.test/api/v1/x/tweets/search", url)
        self.assertIn("limit=100", url)
        self.assertIn("queryType=Latest", url)
        self.assertIn("sinceTime=2026-01-01", url)

    def test_normalizes_nested_tweet_payload(self) -> None:
        payload = {
            "data": {
                "tweets": [
                    {
                        "id": "123",
                        "text": "hello",
                        "public_metrics": {
                            "like_count": 5,
                            "retweet_count": "7",
                            "reply_count": 2,
                        },
                        "author": {"username": "alice", "id": "42"},
                    }
                ]
            }
        }
        self.assertEqual(
            normalize_search_payload(payload),
            [
                {
                    "id": "123",
                    "text": "hello",
                    "createdAt": None,
                    "retweetCount": 7,
                    "favoriteCount": 5,
                    "replyCount": 2,
                    "userScreenName": "alice",
                    "userId": "42",
                    "url": None,
                    "raw": payload["data"]["tweets"][0],
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
