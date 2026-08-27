# Packages the Discovery Net application and its pinned CometBFT process adapter.

FROM cometbft/cometbft:v0.40.0 AS cometbft

FROM python:3.12-slim

COPY --from=cometbft /usr/bin/cometbft /usr/local/bin/cometbft

WORKDIR /opt/discovery-net
COPY pyproject.toml ./
COPY src ./src
RUN python -m pip install --no-cache-dir . \
    && groupadd --system discovery \
    && useradd --system --gid discovery --home-dir /var/lib/discovery discovery \
    && install -d -o discovery -g discovery /var/lib/discovery /var/lib/cometbft

USER discovery
STOPSIGNAL SIGTERM

CMD ["discovery-node", "--help"]
