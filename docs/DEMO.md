# Demo walkthrough

The demo video runs 1:50. Almost all of it is the CPU app on the three bundled examples. The one generation on screen is a recorded run of the hangar board on an RTX 4090, played as a time-lapse. Every example image was rendered on that same RTX 4090.

| Time | On screen |
|---|---|
| 0:00–0:05 | The continuity example's landscape storyboard |
| 0:05–0:14 | Home: the featured greenhouse board and the three example cards |
| 0:14–0:16 | The current CPU app's New scene form with Character, Key prop and Set blank, labeled "CPU APP · SAME BUILD" |
| 0:16–0:34 | The recorded hangar run, labeled "RECORDED RUN · RTX 4090 · TIME-LAPSE": the sentence filled in, **Build shot list**, **Render board**, and the queue counting up to twelve takes |
| 0:34–0:42 | The hangar close-up and its Fail verdict: made from text alone, the robot turned into a human face |
| 0:42–0:56 | The greenhouse continuity board, **Render & continuity** and the hero badge on 02 Medium |
| 0:56–1:11 | **Compare & pick** on 04 Over shoulder: SDXL T01 at 3.762 s, the failed T02, and the selected Qwen T03 at 83.106 s, reviewed Fail with a note |
| 1:11–1:23 | The six cards and their verdicts; 5 of 6 cuts match their shot type, counting hand-edited prompts and one SDXL fallback |
| 1:23–1:33 | The "How it works" diagram from the README |
| 1:33–1:42 | A portrait storyboard PNG and the export ZIP's `manifest.json` |
| 1:42–1:50 | End card |

## Follow the same path yourself

Everything except rendering works in the CPU app with no GPU. Start it as in [Try it without a GPU](../README.md#try-it-without-a-gpu).

1. On the home page, choose **Explore the board** on the hangar example and open the close-up card to read its Fail verdict and note.
2. Explore the greenhouse continuity example. Open **Render & continuity** and find the hero badge on 02 Medium (S02/T05).
3. Open **Compare & pick** on 04 Over shoulder. Compare the SDXL take, the failed slot and the selected Qwen edit with their seeds and times. Save a verdict and a note; reviews are saved with the board.
4. Click **Storyboard ↗**, switch to Portrait and click **Download PNG**. Then click **Export ZIP ↓** and open `manifest.json` to see the hero hash, model hashes, seeds and reviews.

Rendering new takes, as in the recorded run, needs the GPU worker described in [SETUP.md](SETUP.md).
