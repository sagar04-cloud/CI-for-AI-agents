FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY pyproject.toml README.md ./
COPY src ./src
COPY profiles ./profiles

RUN pip install --no-cache-dir .

ENTRYPOINT ["donegate"]
CMD ["--help"]
