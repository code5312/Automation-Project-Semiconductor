# Brings up the docker-compose stack (api + dashboard) and opens a Cloudflare
# Quick Tunnel to the dashboard's host port so people outside this machine
# can reach it over HTTPS while this window stays open. No Cloudflare
# account/login needed -- `cloudflared tunnel --url` issues a free, random
# *.trycloudflare.com URL for the session (it cannot be pinned to a chosen
# subdomain -- that requires a named tunnel on a domain you own).
#
# Use this instead of start-external.ps1 when you're running the stack via
# `docker compose` rather than the local .venv -- docker-compose.yml already
# binds the dashboard to 0.0.0.0:8501 on the host, so this script only needs
# to add the tunnel on top of it.
#
# Requirements: cloudflared on PATH (installed via
# `winget install --id Cloudflare.cloudflared -e`), and Docker Desktop running.
#
# Usage (from the project root):
#   ./scripts/start-external-docker.ps1
#
# Stop with Ctrl+C -- this kills the tunnel and runs `docker compose down`,
# so the public URL stops working immediately.
#
# Security note: this exposes the dashboard (defect-event data, and any
# Anthropic API calls triggered from the "AI 요약" button) to anyone who
# has the URL. The URL is unlisted but not access-controlled, so only share
# it with people who should see this data, and stop the tunnel when done.

$ErrorAction = "Stop"

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Error "cloudflared not found on PATH. Install it with: winget install --id Cloudflare.cloudflared -e"
    exit 1
}

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

Write-Output "Starting docker compose (api + dashboard)..."
docker compose up --build -d

try {
    Write-Output "Waiting for the dashboard to come up..."
    Start-Sleep -Seconds 5
    Write-Output "Opening Cloudflare Quick Tunnel to http://localhost:8501 ..."
    & cloudflared tunnel --url http://localhost:8501
}
finally {
    Write-Output "Stopping docker compose..."
    docker compose down
}
