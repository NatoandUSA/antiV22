"""Google Trends momentum checker (free data source)."""
import time
from pytrends.request import TrendReq


def fetch_momentum(keywords, geo="US", retries=3):
    """Return {keyword: {"avg_interest": float, "momentum_pct": float}}.

    momentum_pct compares the last ~3 months vs the first ~3 months
    of a 12-month window. Positive = rising niche.
    """
    pytrends = TrendReq(hl="en-US", tz=0)
    results = {}

    for i in range(0, len(keywords), 5):  # Google allows 5 per request
        batch = keywords[i:i + 5]
        df = None
        for attempt in range(retries):
            try:
                pytrends.build_payload(batch, timeframe="today 12-m", geo=geo)
                df = pytrends.interest_over_time()
                break
            except Exception as exc:
                wait = 15 * (attempt + 1)
                print(f"  Google Trends hiccup ({exc}). Retrying in {wait}s...")
                time.sleep(wait)
        if df is None or df.empty:
            print(f"  Skipping batch (no data): {batch}")
            continue

        for kw in batch:
            if kw not in df.columns:
                continue
            series = df[kw]
            earlier = series.head(13).mean()
            recent = series.tail(13).mean()
            momentum = ((recent - earlier) / earlier * 100) if earlier > 0 else 0.0
            results[kw] = {
                "avg_interest": round(float(series.mean()), 1),
                "momentum_pct": round(float(momentum), 1),
            }
        time.sleep(5)  # be polite; avoids rate limiting

    return results
