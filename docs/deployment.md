# Deployment Guide

This document outlines how to deploy Tri-Netra Forensics. The deployment architecture relies on Docker for containerization, ensuring consistency across development and production environments.

## 1. Prerequisites
- **Docker**: Engine 24.0+
- **Docker Compose**: V2+
- **Ports**: 3000 (Frontend), 10000 (Backend API) must be available on the host machine.

## 2. Environment Configuration
The backend requires a `.env` file to function properly, primarily for the AI Copilot.

Create `backend/.env`:
```env
# Groq API Keys for the Investigative Copilot
GROQ_API_KEY_1=gsk_your_primary_key_here
GROQ_API_KEY_2=gsk_your_fallback_key_here
```

## 3. Local Development Deployment
For active development without Docker:

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 10000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```
The workspace will be available at `http://localhost:3000`.

## 4. Production Deployment (Docker Compose)
The root directory contains a `docker-compose.yml` file that orchestrates the entire stack.

```bash
# Build and start the containers in detached mode
docker-compose up --build -d
```

### Container Topology
* **`trinetra-backend`**: Runs the FastAPI application using Gunicorn/Uvicorn workers. Maps internal port 10000 to host port 10000.
* **`trinetra-frontend`**: Builds the Next.js static output and serves it, or runs the Next.js production server. Maps internal port 3000 to host port 3000.

### Persistent Storage
In the Docker environment, the `backend.db` state file is persisted via a Docker volume mounted to the backend container. This ensures that restarting the containers does not wipe the active investigation data.

## 5. Reverse Proxy (Nginx)
For a true production setup, an Nginx reverse proxy is recommended to handle SSL termination and route traffic:
* `/` -> Routes to the Next.js frontend (Port 3000)
* `/api/` -> Routes to the FastAPI backend (Port 10000)

An example `nginx.conf` is provided in the repository root.
