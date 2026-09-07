## SEO Keyword Intelligence

Keyword generation uses the existing Groq integration for product-grounded,
geography-neutral candidates, then enriches them with real Google keyword data
from DataForSEO. Metrics are cached by normalized keyword, ISO country,
language, and provider, so cached values are never shared between markets.

Required backend environment variables:

```env
DATAFORSEO_LOGIN=your_dataforseo_login
DATAFORSEO_PASSWORD=your_dataforseo_password
```

The live endpoint is DataForSEO's Google Search Volume API. A request can use
the stored profile market or an optional `market` ISO code (`PK`, `US`, `GB`,
`AE`, `AU`, `CA`) and `language` code (`en`). No SEO metrics are fabricated:
missing metrics are shown as `N/A`, and an unavailable provider returns an API
error unless all requested values are already cached.
