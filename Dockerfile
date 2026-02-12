FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libsndfile1 \
        libportaudio2 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry

WORKDIR /app

COPY pyproject.toml poetry.lock* ./
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --no-root

COPY src/ src/
COPY styles/ styles/

RUN poetry install --no-interaction --no-ansi

EXPOSE 9878

ENTRYPOINT ["rubin"]
