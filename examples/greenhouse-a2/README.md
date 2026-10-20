# Greenhouse — SDXL and frozen-hero continuity

| Field | Value |
|---|---|
| Device | NVIDIA GeForce RTX 4090 × 1 |
| Scene | A traveler discovers a small brass compass in a rain-soaked greenhouse. |
| Cuts | 6 |
| Attempts | 23 |
| Published source PNGs | 18 |
| SDK seconds: sum | 625.206 |
| SDK seconds: range | 0.018–100.425 |
| Timing scope | Upload, load/unload, encoding, sampling, polling, download/save; excludes setup, queue wait, preflight hashing and visual review |
| Models | Pinned repository locks; public weights; ComfyUI offline, partner nodes disabled |
| SDXL attempts | 13 |
| Hero candidates | 8 |
| Frozen hero | s02/t05; seed 20679936 |
| Qwen attempts / cap | 10 / 10 |
| Qwen selected / unselected attempts | 4 / 6 |
| Qwen downloaded / SDK failures | 5 / 5 |
| Initial queue transport failure | One returned image, one engine-completed job without SDK download, three submissions without remote jobs; all five attempt slots retained |
| First Qwen framing PASS, including hero | 1/6 |
| Final framing PASS, including hero | 5/6 |
| Qwen settings | Edit-2511 Q8_0 + VL-7B Q8_0 + F16 projector + Qwen VAE; 24 steps; CFG 4; Euler/simple; shift 3.1; denoise 1; 1MP reference; no LoRA |
| Reference policy | Every Qwen edit uses the same frozen SDXL original; edits are never chained |
| Final selection methods | 4 Qwen edits + 1 reused SDXL hero + 1 SDXL fallback (S06) |
| S06 status | Both Qwen attempts failed SDK delivery; final pick is the new RTX 4090 SDXL baseline |
| Review notation | PASS: visibly compatible; FAIL: observed mismatch; FAIL†: hidden/small/blurred, unverified; hero comparisons use the baseline image |
| Review API | Every attempt has a stored manual verdict and note through PUT take review |

## SDXL first takes and selected hero

| Cut / take | Face | Outfit | Prop | Set | Framing | Observation |
|---|---|---|---|---|---|---|
| s01/t01 | FAIL† | PASS | FAIL† | FAIL | PASS | Distant rear figure hides face and compass; yellow coat visible. Large symmetrical arched space differs from the hero view. |
| s02/t05 | PASS | PASS | PASS | PASS | PASS | Chosen baseline: entire head, torso and waist/hips visible, hands holding an open brass compass. Yellow coat and teal scarf. Brown satchel not visible. |
| s03/t01 | FAIL | FAIL† | FAIL† | FAIL† | PASS | Extreme face detail has a different apparent face; clothing, prop and architecture cannot be checked. |
| s04/t01 | FAIL† | FAIL | FAIL | PASS | FAIL | Rear figure wears a tan jacket and handles a box-like device; figure is in the right foreground, not the requested left. |
| s05/t01 | FAIL† | FAIL† | FAIL | FAIL† | PASS | Macro framing succeeds; black-and-gold compass rose/ring differs from the hero white dial and open case. |
| s06/t01 | FAIL† | PASS | FAIL† | FAIL | PASS | Strong upward view with a small yellow-coated figure; new domed stairwell architecture; face and prop unverified. |

## First Qwen board, including reused hero

| Cut / take | Face | Outfit | Prop | Set | Framing | Observation |
|---|---|---|---|---|---|---|
| s01/t02 | FAIL† | PASS | FAIL† | PASS | FAIL | Figure is about one third of image height, above the requested one-fifth maximum. Visible glass/wood/fern motifs match; off-screen layout and small face/dial are unverified. |
| s02/t05 | PASS | PASS | PASS | PASS | PASS | Chosen baseline: entire head, torso and waist/hips visible, hands holding an open brass compass. Yellow coat and teal scarf. Brown satchel not visible. |
| s03/t02 | FAIL† | FAIL† | FAIL† | FAIL† | FAIL† | SDK transport failed before output download; no published image to review. Engine log records a completed job after the connection failed. |
| s04/t02 | FAIL† | FAIL† | FAIL† | FAIL† | FAIL† | SDK transport failed before output download; no published image to review. Submission did not reach a remote job. |
| s05/t02 | FAIL† | FAIL† | FAIL† | FAIL† | FAIL† | SDK transport failed before output download; no published image to review. Submission did not reach a remote job. |
| s06/t02 | FAIL† | FAIL† | FAIL† | FAIL† | FAIL† | SDK transport failed before output download; no published image to review. Submission did not reach a remote job. |

## Final picks

| Cut / take | Face | Outfit | Prop | Set | Framing | Observation |
|---|---|---|---|---|---|---|
| s01/t03 | FAIL† | PASS | FAIL† | PASS | FAIL | Figure remains about one quarter of image height, above the requested one-eighth maximum. Yellow/teal clothing and glass/wood/fern motifs match; face, dial and new room layout are unverified. |
| s02/t05 | PASS | PASS | PASS | PASS | PASS | Chosen baseline: entire head, torso and waist/hips visible, hands holding an open brass compass. Yellow coat and teal scarf. Brown satchel not visible. |
| s03/t03 | PASS | PASS | FAIL† | FAIL† | PASS | Apparent face and short side-parted hair are compatible; teal scarf/yellow collar edges remain. Prop and set are outside this tight face crop. |
| s04/t03 | FAIL† | PASS | FAIL | PASS | PASS | Left-foreground rear shoulder and head satisfy OTS. Yellow coat, teal scarf and wet glass/ferns match. Compass dial moves onto the hinged upper half, changing the case design. |
| s05/t03 | FAIL† | FAIL† | FAIL† | FAIL† | PASS | Macro contains only hands and compass, with a blurred yellow background. White dial, gold rim and open lid are compatible; exact needle arrangement cannot be verified against the smaller hero detail. |
| s06/t01 | FAIL† | PASS | FAIL† | FAIL | PASS | Strong upward view with a small yellow-coated figure; new domed stairwell architecture; face and prop unverified. Selected SDXL fallback: neither Qwen attempt delivered an image. |

## Measured timings

| Metric | SDK seconds |
|---|---|
| SDXL all attempts | 44.001 |
| Qwen all attempts including failures | 581.205 |
| Qwen successful downloads | 450.766 |
| Qwen successful-download mean | 90.153 |
| Qwen successful-download range | 80.000–100.425 |
| Qwen selected edits | 350.341 |

| Cut / take | Method | Seed | SDK status | Seconds | Selected |
|---|---|---|---|---|---|
| s01/t01 | sdxl-base | 20261020 | succeeded | 3.588 | False |
| s01/t02 | qwen-reference | 20261020 | succeeded | 100.425 | False |
| s01/t03 | qwen-reference | 20261022 | succeeded | 96.814 | True |
| s02/t01 | sdxl-base | 20261020 | succeeded | 3.722 | False |
| s02/t02 | sdxl-base | 20365749 | succeeded | 3.649 | False |
| s02/t03 | sdxl-base | 20470478 | succeeded | 2.638 | False |
| s02/t04 | sdxl-base | 20575207 | succeeded | 2.662 | False |
| s02/t05 | sdxl-base | 20679936 | succeeded | 3.667 | True |
| s02/t06 | sdxl-base | 20784665 | succeeded | 3.709 | False |
| s02/t07 | sdxl-base | 20889394 | succeeded | 2.671 | False |
| s02/t08 | sdxl-base | 20994123 | succeeded | 2.836 | False |
| s03/t01 | sdxl-base | 20261020 | succeeded | 3.697 | False |
| s03/t02 | qwen-reference | 20261020 | failed | 58.752 | False |
| s03/t03 | qwen-reference | 20261021 | succeeded | 80.0 | True |
| s04/t01 | sdxl-base | 20261020 | succeeded | 3.762 | False |
| s04/t02 | qwen-reference | 20261020 | failed | 0.128 | False |
| s04/t03 | qwen-reference | 20261021 | succeeded | 83.106 | True |
| s05/t01 | sdxl-base | 20261020 | succeeded | 3.777 | False |
| s05/t02 | qwen-reference | 20261020 | failed | 0.018 | False |
| s05/t03 | qwen-reference | 20261021 | succeeded | 90.421 | True |
| s06/t01 | sdxl-base | 20261020 | succeeded | 3.623 | True |
| s06/t02 | qwen-reference | 20261020 | failed | 0.024 | False |
| s06/t03 | qwen-reference | 20261021 | failed | 71.517 | False |

| File | Data |
|---|---|
| board.json | Every attempt, snapshot, pick and stored review |
| takes/; workflows/ | Source PNGs and portable graphs; submitted graphs for Qwen |
| selects.zip; export/ | Selected frames, graphs, manifest and two storyboards |
| timing.csv; provenance.json | Measured per-attempt timing; device and PNG hashes |
| contact-sheet.png | All attempts, original proportions |
| hero-contact-sheet.png; hero-review.json | All hero candidates and medium-framing review |
| sdxl-board.json; sdxl-selects.zip | SDXL picks before continuity |
| sdxl-review.json; first-qwen-review.json; final-review.json | Separate face/outfit/prop/set/framing judgments |
| attempt-review.json; continuity-review.json | All detailed attempt observations; all API-saved verdicts |
| continuity-vs-sdxl.png | SDXL picks versus final reference picks |
| qwen-attempts.png; all-qwen-runs.png | First versus final; every Qwen attempt |
| before-after-sheet.png | Early recipe versus coverage recipe, both re-rendered on this same RTX 4090; settings differ |
