# Kalshi Value Finder — website edition

Mobile-friendly Kalshi public market scanner. No API key needed. Shows live public quotes when the Kalshi API is reachable. This is **not** an independently trained prediction model and cannot identify guaranteed profitable bets.

## Publish on Render

1. Create a GitHub repository and upload `index.html`, `server.py`, and `render.yaml` to the repository root.
2. On https://dashboard.render.com select **New > Blueprint** and connect that GitHub repository.
3. Review the service settings and deploy. Render provides a public `onrender.com` URL when deployment succeeds.
4. Open that URL on your iPhone. In Safari, choose Share > Add to Home Screen if desired.

Render pricing and free tier availability may change. This project does not include a domain name or an already deployed live URL.

## Run locally

`python3 server.py`, then visit `http://127.0.0.1:8765`. No packages required.

## Notes

The `/api/markets` endpoint proxies Kalshi public market data. The browser requests up to the selected number of 200-market pages, not necessarily every open market. Some category labels are inferred from ticker prefixes. Displayed quotes can be stale; verify on Kalshi. Expected value requires **your own** probability estimate and excludes fees, spread, and slippage. No bets are placed.

Before scaling public usage, add request throttling, caching, observability, and further security hardening.
