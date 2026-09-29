# Single image for both runtime surfaces (API and dashboard) -- they share
# the same dependencies and codebase, so docker-compose.yml picks the
# command per service instead of maintaining two near-identical images.
FROM python:3.11-slim

# fonts-nanum installs NanumGothic at /usr/share/fonts/truetype/nanum/, which
# is already the Linux fallback path in src/report/pdf.py's font search list
# -- without it, PDF reports fall back to ReportLab's non-embedded CID fonts,
# which render Korean text as blank glyphs in viewers without a matching
# system font (see README's PDF section for how that was found and fixed).
RUN apt-get update && apt-get install -y --no-install-recommends fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# data/ (SECOM/vibration/WM-811K, including the 2GB LSWMD.pkl) and output/
# (SQLite DB, generated reports) are runtime state, not image content --
# both are .dockerignore'd and expected to be bind-mounted (see
# docker-compose.yml and the README's Docker section).
VOLUME ["/app/data", "/app/output"]

EXPOSE 8000 8501
