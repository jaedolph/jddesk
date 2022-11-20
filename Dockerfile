FROM python:3.9-slim-bullseye

WORKDIR /usr/src/app

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    pkg-config \
    libboost-python-dev \
    libboost-thread-dev \
    libbluetooth-dev \
    libglib2.0-dev \
    python3.9-dev \
    && rm -rf /var/lib/apt/lists/*
COPY . /usr/src/app
RUN pip install --no-cache-dir .

USER 1001

CMD jddesk-controller
