FROM python:3.11-slim

WORKDIR /usr/src/app

RUN apt-get update && apt-get install -y \
    bluez \
    && rm -rf /var/lib/apt/lists/*
COPY . /usr/src/app
RUN pip install --no-cache-dir .

USER 1001

CMD ["jddesk"]
