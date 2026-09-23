# PR #21 corrective design

This sequence supersedes the original diagram for revision 2 while preserving the original artifact. It describes `specs/hyperliquid-native-trailing.md` corrective contract; runtime correctness is verified separately. Conditional outcome rows distinguish rejection/no ID, open waiting, active matching readback, and accepted-order termination.

- Before entry, persist a distance normalized by its own significant figures and metadata decimal precision; reject zero before exposure.
- Rejected or unacknowledged trailing submission retains fixed SL monitoring under intervention, without automatic resubmission/adoption. Explicit exit, fixed-SL loss, and cleanup remain available in this specific intervention mode.
- Verified full-sized open waiting orders stay PROTECTING with zero active coverage and no timeout exit solely for waiting. Matching active orders become PROTECTED.
- Previously accepted native order termination triggers residual exit; flat cleanup confirms both stops terminal.
- Parse known clauses independently, then require requested quote distance and immediate activation.

Validation: all 9 showcase checks passed, zero composition errors/warnings. Delivery binds exact specification and HTML bytes in `delivery.json`. Automated Chromium evidence passes containment at 1440x900, 1600x1000, 1920x1080, and 2048x1320. Both endpoint sizes were captured in light/dark themes and visually inspected; `perceptual-review.json` records that separate judgment. No composition correction rounds were needed.

The initial sandbox validation could not spawn its subprocess; the authorized local subprocess retry passed. The initial browser invocation used an unsupported environment-variable name and skipped capture; the supported `ARCHIFY_CHROME` retry passed and replaced the artifact-bound browser receipt. No network publication or live exchange action was performed.
