FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    bubblewrap git make ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY requirements.lock requirements.lock
RUN python -m pip install --no-cache-dir -r requirements.lock
COPY . .
RUN ./scripts/setup_benchmark.sh

CMD ["make", "audit"]
