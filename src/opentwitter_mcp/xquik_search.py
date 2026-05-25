"""Optional Xquik search backend."""

import os
from typing import Any, Optional

import httpx

DEFAULT_BASE_URL = "https://xquik.com"
REQUEST_TIMEOUT_SECONDS = 30.0


def resolve_search_backend(value: str = "") -> str:
    """Return the selected search backend."""
    requested = value or os.environ.get("TWITTER_SEARCH_BACKEND", "")
    normalized = requested.strip().lower().replace("_", "-")
    if normalized == "xquik":
        return "xquik"
    return "default"


async def search_tweets_with_xquik(
    *,
    keywords: Optional[str] = None,
    from_user: Optional[str] = None,
    to_user: Optional[str] = None,
    mention_user: Optional[str] = None,
    hashtag: Optional[str] = None,
    exclude_replies: bool = False,
    exclude_retweets: bool = False,
    min_likes: int = 0,
    min_retweets: int = 0,
    min_replies: int = 0,
    since_date: Optional[str] = None,
    until_date: Optional[str] = None,
    lang: Optional[str] = None,
    product: str = "Top",
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """Search tweets through Xquik and return OpenTwitter-style records."""
    api_key = _resolve_api_key()
    url = _build_search_url(
        query=_build_search_query(
            keywords=keywords,
            from_user=from_user,
            to_user=to_user,
            mention_user=mention_user,
            hashtag=hashtag,
            exclude_replies=exclude_replies,
            exclude_retweets=exclude_retweets,
            min_likes=min_likes,
            min_retweets=min_retweets,
            min_replies=min_replies,
            lang=lang,
        ),
        since_date=since_date,
        until_date=until_date,
        product=product,
        max_results=max_results,
    )
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.get(url, headers=_auth_headers(api_key))
        response.raise_for_status()
        return normalize_search_payload(response.json())


def normalize_search_payload(payload: Any) -> list[dict[str, Any]]:
    """Normalize supported Xquik payload shapes into this server's tweet shape."""
    return [_normalize_tweet(tweet) for tweet in _collect_tweets(payload)]


def _resolve_api_key() -> str:
    api_key = os.environ.get("XQUIK_API_KEY")
    if not api_key or not api_key.strip():
        raise ValueError("Xquik search requires XQUIK_API_KEY")
    return api_key.strip()


def _auth_headers(api_key: str) -> dict[str, str]:
    if api_key.lower().startswith("bearer "):
        return {"Authorization": api_key, "Accept": "application/json"}
    if api_key.startswith("xq_"):
        return {"x-api-key": api_key, "Accept": "application/json"}
    return {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}


def _build_search_url(
    *,
    query: str,
    since_date: Optional[str],
    until_date: Optional[str],
    product: str,
    max_results: int,
) -> str:
    base_url = (
        os.environ.get("XQUIK_BASE_URL")
        or DEFAULT_BASE_URL
    ).rstrip("/")
    params: dict[str, str] = {
        "q": query or "*",
        "limit": str(min(max(1, max_results), 100)),
        "queryType": "Latest" if product.lower() == "latest" else "Top",
    }
    if since_date:
        params["sinceTime"] = since_date
    if until_date:
        params["untilTime"] = until_date
    request = httpx.URL(f"{base_url}/api/v1/x/tweets/search", params=params)
    return str(request)


def _build_search_query(
    *,
    keywords: Optional[str],
    from_user: Optional[str],
    to_user: Optional[str],
    mention_user: Optional[str],
    hashtag: Optional[str],
    exclude_replies: bool,
    exclude_retweets: bool,
    min_likes: int,
    min_retweets: int,
    min_replies: int,
    lang: Optional[str],
) -> str:
    parts: list[str] = []
    if keywords:
        parts.append(keywords.strip())
    if from_user:
        parts.append(f"from:{_clean_handle(from_user)}")
    if to_user:
        parts.append(f"to:{_clean_handle(to_user)}")
    if mention_user:
        parts.append(f"@{_clean_handle(mention_user)}")
    if hashtag:
        parts.append(f"#{hashtag.lstrip('#').strip()}")
    if exclude_replies:
        parts.append("-filter:replies")
    if exclude_retweets:
        parts.append("-filter:retweets")
    if min_likes > 0:
        parts.append(f"min_faves:{min_likes}")
    if min_retweets > 0:
        parts.append(f"min_retweets:{min_retweets}")
    if min_replies > 0:
        parts.append(f"min_replies:{min_replies}")
    if lang:
        parts.append(f"lang:{lang.strip()}")
    return " ".join(part for part in parts if part)


def _collect_tweets(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("tweets", "data", "results", "items", "statuses"):
        nested = payload.get(key)
        tweets = _collect_tweets(nested)
        if tweets:
            return tweets
    for value in payload.values():
        tweets = _collect_tweets(value)
        if tweets:
            return tweets
    return []


def _normalize_tweet(tweet: Any) -> dict[str, Any]:
    if not isinstance(tweet, dict):
        return {"raw": tweet}
    author = _first_dict(tweet, "author", "user")
    metrics = _first_dict(tweet, "public_metrics", "metrics")
    return {
        "id": _first_value(tweet, "tweet_id", "id", "id_str", "rest_id"),
        "text": _first_value(tweet, "source_full_text", "full_text", "text", "content"),
        "createdAt": _first_value(tweet, "created_at", "createdAt", "timestamp", "time"),
        "retweetCount": _metric(tweet, metrics, "retweet_count", "retweets", "reposts"),
        "favoriteCount": _metric(tweet, metrics, "like_count", "favorite_count", "likes"),
        "replyCount": _metric(tweet, metrics, "reply_count", "replies"),
        "userScreenName": _first_value(tweet, "userScreenName", "screen_name", "username")
        or _first_value(author, "screen_name", "username"),
        "userId": _first_value(tweet, "author_id", "userId") or _first_value(author, "id"),
        "url": _first_value(tweet, "url", "tweet_url", "link"),
        "raw": tweet,
    }


def _first_dict(source: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = source.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _first_value(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = source.get(key)
        if value not in (None, ""):
            return value
    return None


def _metric(tweet: dict[str, Any], metrics: dict[str, Any], *keys: str) -> int:
    for source in (metrics, tweet):
        for key in keys:
            value = source.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
    return 0


def _clean_handle(value: str) -> str:
    return value.strip().lstrip("@")
