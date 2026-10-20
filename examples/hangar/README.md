# Hangar — SDXL coverage

| Field | Value |
|---|---|
| Device | NVIDIA GeForce RTX 4090 × 1 |
| Scene | A gray utility robot with a square metal head, a single blue optical sensor and mechanical gripper arms repairs a small spaceship engine on a workbench in a quiet hangar at night. |
| Cuts | 6 |
| Attempts | 12 |
| Published source PNGs | 12 |
| SDK seconds: sum | 62.295 |
| SDK seconds: range | 2.606–22.981 |
| Timing scope | Upload, load/unload, encoding, sampling, polling, download/save; excludes setup, queue wait, preflight hashing and visual review |
| Models | Pinned repository locks; public weights; ComfyUI offline, partner nodes disabled |
| Character / prop / set extra inputs | empty / empty / empty |
| Coverage | 6 cuts × 2 takes |
| Prompt edits | No cut prompt edits; a more explicit single scene sentence was used for this second study |
| Earlier studies | 12 additional discarded SDXL takes are retained in the run artifacts, outside this example |
| Visual limitations | Human/cyborg faces, human workers or fingers, and missing robot action remain in several cuts; selected take notes record these failures |
| Prompt contamination check | 0 traveler / greenhouse / compass / raincoat occurrences in positive prompts |
| Selection | Manual visual review; one selected take per cut |
| Continuity | SDXL only; no frozen reference or identity guarantee |

| Cut | Selected take | Seed | SDK seconds | Review |
|---|---|---|---|---|
| s01 Establishing | t01 | 20261020 | 22.981 | Wide hangar and a small mechanical subject at a workbench; spaceship engine detail is weak. |
| s02 Medium | t02 | 20365749 | 2.868 | Head and torso of a mechanical robot at an engine workbench; exact single-sensor design is not retained. |
| s03 Close-up | t02 | 20365749 | 3.703 | Close-up framing, but a humanoid cyborg face replaces the requested square metal head. |
| s04 Over shoulder | t01 | 20261020 | 3.770 | Foreground robot and engine equipment, but left-shoulder OTS fails and human workers appear. |
| s05 Insert | t02 | 20365749 | 3.799 | Macro mechanical engine detail; robot gripper action is not visible. |
| s06 Low angle | t02 | 20365749 | 2.606 | Low-angle engine structure, but robot repair action is absent. |

| File | Data |
|---|---|
| board.json | Every attempt, snapshot, pick and stored review |
| takes/; workflows/ | Source PNGs and portable graphs; submitted graphs for Qwen |
| selects.zip; export/ | Selected frames, graphs, manifest and two storyboards |
| timing.csv; provenance.json | Measured per-attempt timing; device and PNG hashes |
| contact-sheet.png | All attempts, original proportions |
