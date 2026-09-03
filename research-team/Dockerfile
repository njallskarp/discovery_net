FROM node:22-bookworm-slim AS frontend

WORKDIR /ui
COPY research-team-ui/package.json research-team-ui/package-lock.json ./
RUN npm ci
COPY research-team-ui ./
RUN npm run build

FROM node:22-bookworm-slim AS codex-cli

ARG CODEX_CLI_VERSION=0.143.0
RUN npm install --global "@openai/codex@${CODEX_CLI_VERSION}"

FROM python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DISCOVERY_RESEARCH_TEAM_ROOT=/var/lib/research-team

RUN apt-get update \
    && apt-get install --yes --no-install-recommends git openssh-client libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 research-team \
    && useradd --uid 10001 --gid research-team --create-home research-team

WORKDIR /opt/discovery-net

COPY pyproject.toml ./
COPY src ./src
COPY --from=frontend /ui/dist ./src/discovery_net/research_team/static
COPY --from=codex-cli /usr/local/bin/node /usr/local/bin/node
COPY --from=codex-cli /usr/local/lib/node_modules/@openai/codex /usr/local/lib/node_modules/@openai/codex
RUN ln -s ../lib/node_modules/@openai/codex/bin/codex.js /usr/local/bin/codex \
    && python -m pip install --no-cache-dir '.[research-team]' \
    && mkdir -p /var/lib/research-team \
    && chown research-team:research-team /var/lib/research-team

USER research-team

EXPOSE 8787

CMD ["research-team-dashboard", "--host", "0.0.0.0", "--port", "8787"]
