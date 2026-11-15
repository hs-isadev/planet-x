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
| Branch | `render-preview` |
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
2. Open the main page and load a SPHEREx field. The hosted service starts with an empty cache. Confirm the frame count, dates, and observed cutouts appear.
3. To test pinning, select a body in **3D Context**, then select a star in **Satellite View** and return to **3D Context**. Only the Satellite selection creates a reticle.
4. Share the `onrender.com` address once these checks pass.

If the build cannot find the Dockerfile, confirm the branch and leave Root Directory blank. If startup fails, use the first error in **Logs**. The Dockerfile defines the startup command and reads Render's `PORT` variable. A long first request can be a Free instance waking up. An IRSA timeout in a sky-field search is separate from the service's own health check.

## 4. Add the optional Groq guide key

In the Render service, open **Environment → Add Environment Variable**. Set the key name to `GROQ_API_KEY` and enter your value there. Choose **Save and deploy** to apply it to the running service. Locally, copy `.env.example` to `.env` and add the value after `GROQ_API_KEY=`. Git and Docker exclude the local secret file.

You can also use **New → Blueprint** and point Render at the repository and `render-preview` branch. Render reads `render.yaml` and prompts you for the Groq key. Use the manual Web Service setup if you want to deploy without supplying a key.

## Storage and local features

- The Free instance can spin down when idle and its filesystem is temporary. Your laptop's saved SPHEREx archive stays local. The hosted app fetches cutouts on demand.
- For a lasting cloud cache, a paid service can mount a disk at `/var/data`. Set `SPHEREX_STORAGE_ROOT=/var/data`. This saves future cloud downloads on the disk.
- Laya's local model weights are not part of the deployment. The hosted app can still use IRSA imagery, the spectral plot, deterministic comparisons, and the partner archive lookups.

[Render deploy walkthrough](https://render.com/docs/your-first-deploy) · [Docker settings](https://render.com/docs/docker) · [Secrets](https://render.com/docs/configure-environment-variables) · [Free instance limits](https://render.com/docs/free)
