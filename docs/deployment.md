# Trinetra / OmniWatcher Backend Deployment Guide

This document outlines the architecture and procedures for deploying the Trinetra FastAPI backend to an Ubuntu server using Docker and GitHub Actions.

## A. Architecture

*   **Frontend:** Next.js (hosted separately).
*   **Backend:** FastAPI running in a Docker container on an Ubuntu 22.04 server.
*   **CI/CD:** GitHub Actions workflows for testing and deployment.
*   **Container Registry:** GitHub Container Registry (GHCR).
*   **Deployment Method:** SSH from GitHub Actions.

## B. Local Development

### Backend
To run the backend locally for development:
```bash
python -m uvicorn backend.api:app --host 0.0.0.0 --port 8000
```
Ensure you have a `.env` file based on `.env.example`.

### Frontend
To run the frontend locally, use the existing Next.js commands:
```bash
cd frontend
npm run dev
```
Configure your `frontend/.env.local` with:
```properties
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## C. Docker Local Test

You can build and test the production Docker image locally to verify it works as expected.

1.  **Build the image:**
    ```bash
    docker build -t trinetra-backend .
    ```
2.  **Run the container (PowerShell):**
    ```powershell
    docker run --rm -p 8000:8000 -v "${PWD}/data:/app/data" trinetra-backend
    ```
3.  **Verify:**
    *   Health check: `http://localhost:8000/health`
    *   Swagger UI: `http://localhost:8000/docs`

## D. GitHub Container Registry (GHCR)

The CI/CD pipeline builds the Docker image and pushes it to GHCR.
*   **Image Naming:** `ghcr.io/<owner>/<repository>-backend`
*   **Tags:** Images are tagged with `latest` and the short commit SHA (e.g., `sha-a1b2c3d`) for reliable rollbacks.
*   **Authentication:** The GitHub Actions workflow uses the built-in `GITHUB_TOKEN` to authenticate and push to GHCR.

## E. GitHub Secrets

For the deployment workflow (`.github/workflows/backend-deploy.yml`) to securely SSH into your Ubuntu server, you must configure the following Repository Secrets in GitHub (`Settings` -> `Secrets and variables` -> `Actions`):

*   `SERVER_HOST`: The IP address or domain name of your Ubuntu server.
*   `SERVER_USER`: The SSH username (e.g., `root`).
*   `SERVER_SSH_KEY`: The private SSH key allowing access to the server.
*   `GHCR_USERNAME`: Your GitHub username for the server to pull images.
*   `GHCR_TOKEN`: A Personal Access Token (PAT) with `read:packages` permission.

## F. Server Preparation

Before the first deployment, you must prepare the Ubuntu server:

1.  **Install Docker:** Ensure Docker is installed (the server currently runs Docker 29.7.2 on Ubuntu 22.04.5 LTS).
2.  **SSH Access:** Ensure the `SERVER_USER` has the corresponding public key in `~/.ssh/authorized_keys`.
3.  **Directory Structure:** Create the deployment directories:
    ```bash
    mkdir -p /opt/trinetra/data/cases
    ```
4.  **Environment Variables:** Create the production `.env` file on the server. **It must never be committed to GitHub. Real API keys and APP_SECRET must never appear in the repository or workflow files.**
    ```bash
    nano /opt/trinetra/.env
    ```
    Populate it with your actual production variables like `GROQ_API_KEY` and `APP_SECRET`. Note: `APP_CORS_ORIGINS` will be updated once the actual frontend production URL is known.

## G. Deployment Flow

When a developer pushes to the `main` branch:

1.  **CI Validation:** The `Backend CI` workflow runs to ensure dependencies install and the app imports correctly.
2.  **Docker Build & Push:** The `Backend Deploy` workflow builds the Docker image and pushes it to GHCR with `latest` and `sha` tags.
3.  **SSH Deployment:** The workflow connects to your Ubuntu server via SSH.
4.  **Update Container:** It pulls the exact commit image (`sha-<commit>`), stops and removes the old `trinetra-backend` container, and starts the new one, mounting `/opt/trinetra/data` to `/app/data`.
5.  **Health Check & Rollback:** It polls `http://localhost:8000/health` for up to 60 seconds. If it fails, the new container is removed and the previous container image is automatically restored to ensure zero prolonged downtime.

## H. Rollback

Because images are tagged by commit SHA, rollback is straightforward:

1.  Identify the desired previous image tag from GHCR (e.g., `sha-old123`).
2.  SSH into your server.
3.  Stop the current container:
    ```bash
    docker stop trinetra-backend
    docker rm trinetra-backend
    ```
4.  Start the previous image:
    ```bash
    docker run -d --name trinetra-backend --restart unless-stopped -p 8000:8000 -v /opt/trinetra/data:/app/data --env-file /opt/trinetra/.env ghcr.io/<owner>/<repository>-backend:sha-old123
    ```
5.  Verify health:
    ```bash
    curl http://localhost:8000/health
    ```

## I. Troubleshooting

If the deployment fails or the backend is unresponsive, SSH into the server and use these commands:

*   **Check container status:** `docker ps -a`
*   **View application logs:** `docker logs trinetra-backend`
*   **Inspect container details:** `docker inspect trinetra-backend`
*   **Manual health check:** `curl http://localhost:8000/health`
*   **List local images:** `docker images`

**Common Issues:**
*   **Container exits immediately:** Check logs (`docker logs trinetra-backend`). Usually due to missing environment variables or a syntax error.
*   **GHCR Authentication Failure:** Ensure the GitHub Actions `GITHUB_TOKEN` has `packages: write` permissions.
*   **Port Conflict:** Ensure port 8000 is not being used by another application.
*   **CORS Errors:** Verify `APP_CORS_ORIGINS` in `/opt/trinetra/.env` matches your production frontend domain (once known).
