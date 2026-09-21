# Proposed unified trading data flow

Source: [specification](../../../../specs/unified-trading-data.md). This diagram is a target design, not a deployed-state claim. Logical store nodes share one SQLite database; they are not separate services or databases.

[Interactive HTML](dataflow.html) · [Exact source JSON](dataflow.json) · [Artifact receipt](delivery.json) · [Browser receipt](browser-result.json) · [Visual assessment](review.json).

Deterministic checks: 9/9 showcase; zero errors/warnings. Browser measurements passed at 1440x900, 1600x1000, 1920x1080 and 2048x1320. Image review inspected light at 1440x900 and dark at 2048x1320. Three initial layout repairs resolved node width, one vertical label and excessive viewBox width before delivery. No post-delivery visual correction was required.

The default browser discovery did not find cached Chromium; rerunning the unchanged tool with ARCHIFY_CHROME pointing to the existing local cache produced the passing receipt. No browser was installed and no renderer was modified.
