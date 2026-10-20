# Real UI captures

All screenshots use the current CPU app in headless Chromium. Source stills in the greenhouse boards and the live hangar queue were rendered on the same RTX 4090 worker.

| Capture | State |
|---|---|
| [01-scene.png](01-scene.png) | Scene input, continuity bible, camera/atmosphere chips |
| [02-shot-list.png](02-shot-list.png) | Stored six-cut plan with preserved take recipes |
| [02-edit-cuts.png](02-edit-cuts.png) | Editable cut prompts and negative prompts |
| [03-rendering.png](03-rendering.png) | Actual hangar SDXL queue |
| [04-board.png](04-board.png) | All twelve takes complete, six picks |
| [05-compare.png](05-compare.png) | Side-by-side takes, picked still and locked seed |
| [06-mobile.png](06-mobile.png) | Responsive 390px board view |

The final board/compare captures were taken after the generation engine was stopped, so the engine-offline badge is expected. Viewing saved takes, picking and exporting remain available.

## Continuity captures

Captures 01–21 were refreshed using the new RTX 4090 outputs. Capture 03 is the live hangar queue; 08 is the live Qwen queue before its transport failure. Completed-board captures were made after pod deletion.

| Capture | State |
|---|---|
| [07-continuity-hero.png](07-continuity-hero.png) | Picked SDXL hero, continuity enabled |
| [08-continuity-rendering.png](08-continuity-rendering.png) | Actual five-slot Qwen queue; later transport failures are retained |
| [09-continuity-board.png](09-continuity-board.png) | Final board: four Qwen edits, SDXL hero and S06 SDXL fallback |
| [10-continuity-compare.png](10-continuity-compare.png) | SDXL, failed attempt and selected Qwen OTS with measured times |
| [11-continuity-mobile.png](11-continuity-mobile.png) | Completed board at 390px width |
