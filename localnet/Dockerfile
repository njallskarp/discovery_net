FROM golang:1.25.0-bookworm@sha256:81dc45d05a7444ead8c92a389621fafabc8e40f8fd1a19d7e5df14e61e98bc1a AS cometbft

RUN CGO_ENABLED=0 GOBIN=/out go install github.com/cometbft/cometbft/cmd/cometbft@v0.40.0

FROM python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid 10001 discovery-net \
    && useradd --uid 10001 --gid discovery-net --no-create-home discovery-net \
    && mkdir -p /run/discovery-net

WORKDIR /opt/discovery-net

COPY pyproject.toml ./
COPY src ./src
COPY --from=cometbft /out/cometbft /usr/local/bin/cometbft

RUN python -m pip install --no-cache-dir .

USER discovery-net
