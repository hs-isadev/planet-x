# Deploy Planet X on Render

Planet X is a FastAPI web service with a Dockerfile. Render provides the listening port and the container binds to `0.0.0.0`. You can launch it without a database or a Groq key.

## 1. Connect GitHub

1. Open the [Render Dashboard](https://dashboard.render.com/) and sign in.
2. Choose **New → Web Service**. Choose GitHub as the source and connect your account if prompted. Grant Render access to `hs-isadev/planet-x` if it asks which repositories to access.
3. Select [hs-isadev/planet-x](https://github.com/hs-isadev/planet-x) and choose **Connect**. If it doesn't appear, check the linked GitHub account and the Render GitHub app's repository access in GitHub settings. Refresh the repository picker after granting access.

## 2. Configure the service

| Render field | Value |
| --- | --- |
| Name | `planet-x-observatory` (or any available name) |
| Branch | `final-parallex-preview` |
| Language | **Docker** |
| Region | Choose a region close to your audience |
| Root Directory | Leave blank |
| Dockerfile Path | `./Dockerfile` |
| Docker Build Context Directory | `.` (the repository root) |
| Docker Command | Leave blank to use the Dockerfile's command |
| Instance Type | **Free** for a preview |
| Health Check Path | `/api/health` (in **Advanced** or service **Settings**) |
| Auto-Deploy | **On Commit** if you want pushes to this branch to redeploy |

Choose **Deploy Web Service**. Watch **Logs** and **Events** until the deploy is live. Render builds and starts the app from the Dockerfile. The dashboard shows the public URL.

## 3. Verify the public site

1. Open the dashboard's assigned `onrender.com` URL. Add `/api/health` and verify the response reports `"status": "ok"` and `"data_source": "IRSA SPHEREx"`.
2. Open the main page and load a SPHEREx field. Open a preset. Its bundled previews and FITS are already available once the deploy is up. Check the frame count and dates, then open a FITS download.
3. To test pinning, select a body in **3D Context**, then select a star in **Satellite View** and return to **3D Context**. Only the Satellite selection creates a reticle.
4. Share the `onrender.com` address once these checks pass.

If the build cannot find the Dockerfile, confirm the branch and leave Root Directory blank. If startup fails, use the first error in **Logs**. The Dockerfile defines the startup command and reads Render's `PORT` variable. A long first request can be a Free instance waking up. An IRSA timeout in a sky-field search is separate from the service's own health check.

## 4. Add the optional Groq guide key

In the Render service, open **Environment → Add Environment Variable**. Set the key name to `GROQ_API_KEY` and enter your value there. Choose **Save and deploy** to apply it to the running service. To choose a model, set optional `GROQ_MODEL`. The app defaults to `openai/gpt-oss-20b` and falls back to `openai/gpt-oss-120b` when the preferred model is unavailable or rate-limited. An optional comma-separated `GROQ_FALLBACK_MODELS` adds alternatives. Locally, copy `.env.example` to `.env` and add the value after `GROQ_API_KEY=`. Git and Docker exclude the local secret file.

You can also use **New → Blueprint** and point Render at the repository and `final-parallex-preview` branch. Render reads `render.yaml` and prompts you for the Groq key. Use the manual Web Service setup if you want to deploy without supplying a key.

## Warm and retain the SPHEREx cache

1. Run `python -m scripts.prefetch_lab --bundle --mirror-only` to download indexed exposures directly from the public AWS mirror. The five presets finish first, followed by other stars in distance order. Add `--daily-only` to prioritize one candidate per UTC date. To recover previously downloaded FITS without requesting archive services, use `--offline` and pass each additional cache directory with `--reuse-cache`. Commit the source and updated `backend/data/spherex-seed/` to your deploy branch. Docker includes the FITS, manifests, and PNGs in the image on both Free and paid Render.
2. The Dockerfile and Blueprint start from the bundled files with background discovery disabled. On an existing service, check **Environment** for an override and set `SPHEREX_PREWARM=0`. Paid services can attach a persistent disk at `/var/data` and set `SPHEREX_STORAGE_ROOT=/var/data` to keep additional downloads.
3. Open `/observation-lab/api/library` on the deployed site. Each prepared field reports stored FITS frames and distinct observing dates separately. The default 10′ view shows one usable exposure per UTC date. Detector and date filters can still display other stored exposures. The `sync` object reports archive discovery and download failures.
4. To force rediscovery from a paid Render service shell, run `python -m scripts.prefetch_lab --force`. Add `--field barnard` to refresh one field. An active automatic warmup already serves this purpose and keeps the disk locked while it writes. Render build and pre-deploy commands cannot write to the attached disk.
5. In SPHEREx View, **Search IRSA** queries the archive even when the field has a snapshot. It can show a preview while the rest downloads. For a previously indexed field the app can fetch verified native pixels from the AWS-hosted SPHEREx public mirror if IPAC is unavailable. A completely new field still needs an archive search or an already indexed detector footprint.

Free Render serves the bundled archive after every startup. Live searches still work while the service runs, and those downloads can be lost on restart or spin-down. Set `SPHEREX_PREWARM=0` to rely on the deploy bundle for defaults and avoid a background archive refresh on every cold start. Live searches still run on demand. Alternate detector, date or field-of-view selections are capped at 60 dated frames.

[Render persistent disks](https://render.com/docs/disks) · [Render free-instance limits](https://render.com/docs/free) · [IRSA archive access](https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-access/)
