# Manual Testing Guide: AI Stitch

Step-by-step guide to manually test the AI prompt-to-video pipeline using the
`/ai-stitch` page in the BeatStitch frontend.

> **Before using this guide**, complete the [Manual UI Validation](development.md#manual-ui-validation)
> steps in `docs/development.md` to confirm the core stack is healthy.

## Prerequisites

- Docker and Docker Compose installed
- *(Optional)* `OPENAI_API_KEY` set in `.env` for real AI planning
  (without it, the UI uses a stub plan so you can still test the full render pipeline)

## 1. Start the Stack

```bash
# From the project root:
./setup.sh   # Choose option 1: Quick start/rebuild
# OR
docker compose up -d --build
```

Wait ~15 seconds for all services to initialize.

Verify services are up:

```bash
curl http://localhost:8080/health
# Expected: {"status": "healthy", ...}
```

## 2. Register / Log In

Open **http://localhost:3001** in your browser.

If you don't have an account:

```bash
curl -X POST http://localhost:8080/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username": "demo", "password": "demo1234"}'
```

Log in at http://localhost:3001/login with those credentials.

## 3. Create a Project (if needed)

On the Dashboard (http://localhost:3001), click **New Project** and give it a name.

## 4. Upload Media Assets

In the project editor, upload at least 2-3 images or video clips via the Media panel.
Wait for processing status to show **"ready"** for each asset.

> **Tip:** You can also use the API directly:
> ```bash
> curl -X POST http://localhost:8080/api/projects/{PROJECT_ID}/media \
>   -H "Authorization: Bearer {TOKEN}" \
>   -F "files=@/path/to/image.jpg"
> ```

## 5. Open the AI Stitch Page

Navigate to **http://localhost:3001/ai-stitch**

Or click **"AI Stitch"** in the top navigation bar.

## 6. Select Project and Assets

1. In the **Project** dropdown, select the project you created.
2. Your uploaded media assets will appear in the asset list.
3. Check the assets you want to include in the video.

## 7. Enter a Prompt and Constraints

In the **Prompt & Constraints** panel:

- **Prompt:** Write a description, e.g.:
  ```
  Create an energetic montage. Show each clip for 3 seconds.
  Use crossfade transitions between clips.
  ```
- **Mode:** Leave as "No audio" unless you've uploaded and analyzed an audio track.
- **Target duration:** Optional -- e.g. `30` seconds.
- **Transition:** Choose `cut` or `crossfade`.
- **Max clips:** Optional limit.

Click **"Generate Plan"**.

> **Without `OPENAI_API_KEY`:** The backend returns a stub EditPlan based on your
> selected assets. The UI displays it and lets you continue to apply + render --
> the full pipeline still works end-to-end.

## 8. Review the Generated Plan

The **Plan Preview** panel shows the EditPlan JSON.

Review:
- Each segment has a `media_id` matching one of your assets
- Durations are reasonable
- Any `warnings` listed below the plan

## 9. Apply the Plan

Click **"Apply Plan"**.

This sends the EditPlan to the backend, which validates it and saves it as the
project's active timeline (EDL).

If validation fails, an error message explains which segments are invalid.

## 10. Render the Video

Click **"Render"**.

The render job is queued and the status panel updates every 2 seconds:

```
Queued -> Running (45%) -> Complete
```

Typical render times: 10-60 seconds depending on clip count and duration.

## 11. View and Download the Result

When complete:
- A **video player** appears with the rendered output.
- Click **"Copy output URL"** to get a direct link to the MP4.
- Or right-click the player -> Save Video.

---

## Troubleshooting

### "API not running" / Cannot connect

```bash
docker compose ps          # Check all containers are Up
docker compose logs backend --tail=50
curl http://localhost:8080/health
```

### "OpenAI key missing" error

The UI will show the stub plan instead. To enable real AI planning:

```bash
# Add to .env:
OPENAI_API_KEY=sk-...

# Restart backend:
docker compose restart backend
```

### Worker not running / render stuck at "queued"

```bash
docker compose logs worker --tail=50
docker compose restart worker
```

### Media assets not showing as "ready"

```bash
docker compose logs worker --tail=100 | grep -i "processing\|error\|thumbnail"
```

Processing images takes ~2-5 seconds. Videos take longer (thumbnail + proxy generation).

### "Validation failed" when applying plan

The AI-generated plan referenced an asset that is not ready or does not belong to the
selected project. Try:
1. Ensure all assets show **"ready"** status before generating a plan.
2. Re-generate the plan (the LLM may produce different IDs on retry).
3. Check the `warnings` field in the Plan Preview panel.

### Reset / start fresh

```bash
./setup.sh   # Choose option 2: Full reset
```
