# exhib image: gallery source and templates, Hugo, FFmpeg, metadata tools
# and static-web-server. One image is the whole app, like the other tier-2
# apps: the infra repo references this image and nothing else. The PVC at
# /data holds the gallery media. This image does not contain media.
# Python comes from the base image; uv installs the exhib package (src/exhib)
# into the project venv.
FROM python:3.15-alpine3.24
COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /usr/local/bin/uv

# A Hugo bump needs new HUGO_SHA256 values (hugo_X_checksums.txt).
# renovate: datasource=github-releases depName=gohugoio/hugo extractVersion=^v(?<version>.*)$
ARG HUGO_VERSION=0.169.0
# A bump also needs new SWS_SHA256 values.
# renovate: datasource=github-releases depName=static-web-server/static-web-server extractVersion=^v(?<version>.*)$
ARG SWS_VERSION=2.44.1
# BuildKit sets TARGETARCH per platform. A default here overrides it.
ARG TARGETARCH
# Hugo extended is glibc-linked. gcompat and libstdc++ let it run on musl.
RUN apk add --no-cache ca-certificates gcompat libstdc++ ffmpeg libheif-tools libwebp-tools exiftool wget tar \
 && case "${TARGETARCH}" in \
      amd64) HUGO_ARCH=amd64 HUGO_SHA256=c41672a0725d307758a132bc94a962e59760eb33f9ba08c991b81f9881d6fa7d SWS_ARCH=x86_64-unknown-linux-musl SWS_SHA256=8f94abd9bc9c6d11240301d7271b95f9ec05b1b3e8509087c86ca8fd0b56fb4e ;; \
      arm64) HUGO_ARCH=arm64 HUGO_SHA256=5b190e5d2836c09efe25cc6249f70bde8a6c5331ef412a4c9137e9d5de89a515 SWS_ARCH=aarch64-unknown-linux-musl SWS_SHA256=28e53e5979735309ec3de685330719a11a0ef339aa06d0f0cd8eff5d973b9dfc ;; \
      *) echo "Unsupported TARGETARCH=${TARGETARCH}" >&2; exit 1 ;; \
    esac \
 && wget -q "https://github.com/gohugoio/hugo/releases/download/v${HUGO_VERSION}/hugo_extended_${HUGO_VERSION}_linux-${HUGO_ARCH}.tar.gz" -O /tmp/hugo.tar.gz \
 && echo "${HUGO_SHA256}  /tmp/hugo.tar.gz" | sha256sum -c - \
 && tar -xzf /tmp/hugo.tar.gz -C /usr/local/bin hugo \
 && wget -q "https://github.com/static-web-server/static-web-server/releases/download/v${SWS_VERSION}/static-web-server-v${SWS_VERSION}-${SWS_ARCH}.tar.gz" -O /tmp/sws.tar.gz \
 && echo "${SWS_SHA256}  /tmp/sws.tar.gz" | sha256sum -c - \
 && mkdir -p /tmp/sws-extract \
 && tar -xzf /tmp/sws.tar.gz -C /tmp/sws-extract \
 && mv "/tmp/sws-extract/static-web-server-v${SWS_VERSION}-${SWS_ARCH}/static-web-server" /usr/local/bin/static-web-server \
 && rm -rf /tmp/sws-extract /tmp/hugo.tar.gz /tmp/sws.tar.gz \
 && chmod 0755 /usr/local/bin/hugo /usr/local/bin/static-web-server

# uv uses the base image Python only. It never downloads one.
# No cache: build runs as root, runtime as 1000. A shared cache dir breaks.
ENV UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python3 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY sws.toml /etc/sws/sws.toml
COPY . /app
# /app stays root-owned: the runtime user (1000) reads it and writes only to
# /data, so a compromised process cannot rewrite its own code.
RUN uv sync --frozen --no-dev
# `exhib` is on PATH: `kubectl exec deploy/exhib -- exhib rebuild` works.
ENV EXHIB_APP=/app \
    EXHIB_DATA=/data \
    SERVER_CONFIG_FILE=/etc/sws/sws.toml \
    PATH=/app/.venv/bin:$PATH
USER 1000:1000
# The venv is complete at build time. Runtime writes nothing to it.
ENTRYPOINT ["exhib", "serve"]
