# Implementation plan and actual changes
1. Update risk capital and add explicit-stop unit calculator with rejecting/rounding tests.
2. Add strategy_tools functions and CLI commands for indicators, setup evidence, initial stops, sizing and decision storage; reuse existing registry and BTC predicate.
3. Guard non-entry actions and stale setup evidence in existing signal authority checks.
4. Install canonical trend-strategy skill and both CLI links; document authoring policy, tools and actual strategy integration. Hermes consumes canonical files; runtime install is outside scope.
5. Run affected tests and one real offline CLI/SQLite smoke; independent verifier reads code/skill and exercises scenarios.
6. Under AK's subsequent explicit request, commit and publish a PR, then ask Grok to review the actual PR and post concise Must Fix and Recommendations findings. Stop before merge.
No managed execution/gateway API changes or production calls. Rollback: stop new tool use, preserve existing signal/position/journal state; no destructive schema migration. Highest risk is mistaking advice for entry authority; rejecting action/freshness tests and inherited supervisor checks cover that boundary.
