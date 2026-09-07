import base64
import os
import re
from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session

from models.seo_result import SEOKeywordMetricCache


class DataForSEOError(Exception):
    pass


@dataclass
class KeywordMetric:
    keyword: str
    search_volume: int | None
    competition: float | None
    competition_index: int | None
    cpc: float | None
    source: str = "dataforseo"


def normalize_keyword(keyword: str) -> str:
    return re.sub(r"\s+", " ", keyword.strip().lower())


def _credentials() -> tuple[str, str]:
    login = (os.getenv("DATAFORSEO_LOGIN") or "").strip()
    password = (os.getenv("DATAFORSEO_PASSWORD") or "").strip()
    if not login or not password:
        raise DataForSEOError("DataForSEO is not configured. Set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD.")
    return login, password


def _value(item: dict, *names):
    for name in names:
        value = item.get(name)
        if value is not None:
            return value
    return None


def _result_items(payload: dict) -> list[dict]:
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        raise DataForSEOError("DataForSEO returned an invalid tasks response.")
    items = []
    for task in tasks:
        if task.get("status_code", 0) >= 40000:
            raise DataForSEOError(task.get("status_message") or "DataForSEO task failed.")
        result = task.get("result") or []
        if isinstance(result, list):
            items.extend(item for item in result if isinstance(item, dict))
    return items


def _to_metric(item: dict) -> KeywordMetric | None:
    info = item.get("keyword_info") if isinstance(item.get("keyword_info"), dict) else {}
    keyword = _value(item, "keyword", "keyword_data") or _value(info, "keyword")
    if isinstance(keyword, dict):
        keyword = keyword.get("keyword")
    if not keyword:
        return None
    return KeywordMetric(
        keyword=normalize_keyword(str(keyword)),
        search_volume=_value(item, "search_volume") if _value(item, "search_volume") is not None else _value(info, "search_volume"),
        competition=_value(item, "competition") if _value(item, "competition") is not None else _value(info, "competition"),
        competition_index=_value(item, "competition_index") if _value(item, "competition_index") is not None else _value(info, "competition_index"),
        cpc=_value(item, "cpc") if _value(item, "cpc") is not None else _value(info, "cpc"),
    )


def fetch_metrics(
    db: Session,
    keywords: list[str],
    country: str,
    language: str = "en",
) -> dict[str, KeywordMetric]:
    """Read market-level cache, then make one live request for all misses."""
    country = normalize_country(country)
    normalized = list(dict.fromkeys(normalize_keyword(k) for k in keywords if k.strip()))
    cached_rows = db.query(SEOKeywordMetricCache).filter(
        SEOKeywordMetricCache.normalized_keyword.in_(normalized),
        SEOKeywordMetricCache.country == country.upper(),
        SEOKeywordMetricCache.language == language.lower(),
        SEOKeywordMetricCache.provider == "dataforseo",
    ).all()
    metrics = {
        row.normalized_keyword: KeywordMetric(
            keyword=row.normalized_keyword,
            search_volume=row.search_volume,
            competition=row.competition,
            competition_index=row.competition_index,
            cpc=row.cpc,
        )
        for row in cached_rows
    }
    missing = [keyword for keyword in normalized if keyword not in metrics]
    if not missing:
        return metrics

    try:
        login, password = _credentials()
    except DataForSEOError:
        if metrics:
            return metrics
        raise
    auth = base64.b64encode(f"{login}:{password}".encode()).decode()
    body = [{
        "keywords": missing[:700],
        "location_name": country_name(country),
        "language_code": language.lower(),
        "search_partners": False,
    }]
    try:
        response = httpx.post(
            "https://api.dataforseo.com/v3/keywords_data/google/search_volume/live",
            json=body,
            headers={"Authorization": f"Basic {auth}"},
            timeout=45,
        )
        if response.status_code in (401, 403):
            raise DataForSEOError("DataForSEO authentication failed. Check DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD.")
        if response.status_code == 402:
            raise DataForSEOError("DataForSEO rejected the request because the account balance is insufficient.")
        if response.status_code == 429:
            raise DataForSEOError("DataForSEO rate limit reached. Please retry later.")
        response.raise_for_status()
        fresh = [_to_metric(item) for item in _result_items(response.json())]
    except DataForSEOError:
        if metrics:
            return metrics
        raise
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        raise DataForSEOError(f"DataForSEO request timed out or failed: {exc}") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise DataForSEOError(f"DataForSEO returned an unusable response: {exc}") from exc

    for metric in (metric for metric in fresh if metric):
        metrics[metric.keyword] = metric
        db.add(SEOKeywordMetricCache(
            normalized_keyword=metric.keyword,
            country=country.upper(),
            language=language.lower(),
            provider="dataforseo",
            search_volume=metric.search_volume,
            competition=metric.competition,
            competition_index=metric.competition_index,
            cpc=metric.cpc,
        ))
    db.commit()
    return metrics


def country_name(country: str) -> str:
    names = {
        "PK": "Pakistan", "US": "United States", "GB": "United Kingdom",
        "AE": "United Arab Emirates", "AU": "Australia", "CA": "Canada",
    }
    code = normalize_country(country)
    if code not in names:
        raise DataForSEOError(f"Unsupported market '{country}'. Use an ISO country code supported by DataForSEO.")
    return names[code]


def normalize_country(country: str) -> str:
    value = country.strip().upper()
    names = {
        "PAKISTAN": "PK", "UNITED STATES": "US", "THE UNITED STATES": "US",
        "USA": "US", "UNITED KINGDOM": "GB", "THE UNITED KINGDOM": "GB",
        "UK": "GB", "UNITED ARAB EMIRATES": "AE", "UAE": "AE",
        "AUSTRALIA": "AU", "CANADA": "CA",
    }
    return names.get(value, value)