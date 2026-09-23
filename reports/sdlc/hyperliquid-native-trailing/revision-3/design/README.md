# PR #21 revision 3 design

This sequence adapts revision 2 with two compact conditional readback outcomes. It models the current specification, not a claim of live exchange validation. Conditional outcome rows are alternatives, not a requirement that every order encounters every row.

| Contract / acceptance criterion | Diagram evidence |
| --- | --- |
| AC2: normalize distance and persist before exposure; single native send | Original steps 1–5 retained |
| AC3: isolated condition syntax failure on otherwise validated owned order | `condition-error` and Retain fixed protection card: native INTERVENTION, zero trailing coverage, no resubmit/adoption; independent fixed SL, SL-loss handling and explicit exit continue |
| AC3: other validation failures remain fatal | `generic-error` and Generic freeze stays strict card: identity, type, side, size, known policy semantics and account evidence mismatch freeze; generic transitions (including deadline/budget) clear the native-only exception |
| AC3: healthy readback recovery | Steps 8–9: matching same-ID waiting/active readback restores PROTECTING/PROTECTED and clears the exception |
| AC3: acknowledged terminal order | Step 10 and Recover by the same ID card: residual exit still occurs even with invalid condition syntax; flat cleanup retains verified ownership |

Transient snapshot transport failure preserves an existing native-only exception for later recovery; it does not broaden the syntax-error classification. Waiting remains zero active trail coverage and never causes timeout exit solely for waiting. Known percentage, distance or activation mismatch is a semantic mismatch and stays under generic freeze.

`consumed-inputs.json` records the actual intent, spec, plan, investigation and prior diagram digests consumed. The existing plan was read as the upstream plan; its revision 3 update remains main-owned. No code, shared SDLC state, commits, publication or live exchange calls were made by this assignment.

`validation.json` and `delivery.json` passed all 9 showcase checks with zero errors/warnings. `native-trailing.visual-check.json` records successful Chromium containment at 1440x900, 1600x1000, 1920x1080 and 2048x1320, plus light/dark captures at both endpoint sizes. Four captures were inspected with the image tool; `perceptual-review.json` records that separate judgment and limitations. No source correction rounds were necessary.

Execution notes: the first authoring command used an unavailable `python` executable and wrote nothing; rerunning with `python3` created the candidate. Initial sandbox validation could not start its subprocess (EPERM). The authorized local subprocess retry passed; delivery and browser capture also ran in that permitted execution context. Installed Archify remained unchanged.
