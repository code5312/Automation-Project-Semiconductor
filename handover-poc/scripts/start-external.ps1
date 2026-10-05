# Starts the dashboard bound to 0.0.0.0 and opens a Cloudflare Quick Tunnel
# so people outside this machine can reach it over HTTPS while this window
# stays open. No Cloudflare account/login needed -- `cloudflared tunnel
# --url` issues a free, random *.trycloudflare.com URL for the session.
#
# Requirements: cloudflared on PATH (installed via
# `winget install --id Cloudflare.cloudflared -e`), and the project's
# virtualenv set up per the README.
#
# Usage (from the project root):
#   ./scripts/start-external.ps1
#
# Stop with Ctrl+C -- this kills both the tunnel and the Streamlit server,
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

$streamlit = Start-Process -FilePath "$projectRoot\.venv\Scripts\python.exe" `
    -ArgumentList "-m", "streamlit", "run", "src/dashboard/메인페이지.py", `
                  "--server.address", "0.0.0.0", "--server.port", "8501" `
    -PassThru -NoNewWindow

try {
    Write-Output "Streamlit started (PID $($streamlit.Id)), waiting for it to come up..."
    Start-Sleep -Seconds 5
    Write-Output "Opening Cloudflare Quick Tunnel to http://localhost:8501 ..."
    & cloudflared tunnel --url http://localhost:8501
}
finally {
    Write-Output "Stopping Streamlit (PID $($streamlit.Id))..."
    Stop-Process -Id $streamlit.Id -Force -ErrorAction SilentlyContinue
}
