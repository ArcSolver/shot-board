# Demo walkthrough

## With a GPU worker

Start the app as in [Run it locally](../README.md#run-it-locally).

1. On the home page, choose **New scene**. Type the scene or press **Use greenhouse scene**, then **Build shot list**.
2. Choose **Render board**. Takes arrive cut by cut.
3. Open **Compare & pick** on 02 Medium. **Pick** an SDXL take, or choose **Import reference** under **Hero** and **Pick** the imported take. Then choose **Use pick as hero**.
4. Back on the board, choose **Render reference edits**. Every other cut goes to Qwen-Image-Edit-2511 with the hero as the reference.
5. Click **Export storyboard**, switch to Portrait and click **Download PNG**. Then click **Download ZIP**.

## Without a GPU

Start the app as in [Try it without a GPU](../README.md#try-it-without-a-gpu).

1. On the home page, choose **Open this board**. The greenhouse board opens with its hero and reference edits in place.
2. Open **Compare & pick** on 02 Medium to see the imported reference picked as the hero.
3. Open **Compare & pick** on 01 Establishing to see its two Qwen reference edits beside the hero.
4. Click **Export storyboard**, switch to Portrait and click **Download PNG**. Then click **Download ZIP** and open `manifest.json` to see the recipes and reviews.
