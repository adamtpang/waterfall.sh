# Public page analytics

The website remains a static deployment. Commit the generated root `site-analytics.js` after changing the tracker or SDK. The `analytics/` source/tool directory is excluded from public deployment.

Set `POSTHOG_PUBLIC_TOKEN` to the public project capture token, then run `npm ci --prefix analytics` and `npm run build --prefix analytics`. Never use a personal/read API key. Dependencies are pinned by the lockfile.

The tracker records only allowlisted public documents on production hosts. Queries, fragments, referrer data, person profiles, autocapture and replay are excluded. PostHog cookieless tracking must be enabled for the project.
