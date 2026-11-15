# exhib image: gallery source and templates, Hugo, FFmpeg, metadata tools
# and static-web-server. One image is the whole app, like the other tier-2
# apps: the infra repo references this image and nothing else. The PVC at
# /data holds the gallery media. This image does not contain media.
FROM alpine:3.22

ARG HUGO_VERSION=0.169.0
ARG SWS_VERSION=2.44.1
# BuildKit sets TARGETARCH per platform. A default here overrides it.
ARG TARGETARCH
# Hugo extended is glibc-linked. gcompat and libstdc++ let it run on musl.
RUN apk add --no-cache ca-certificates gcompat libstdc++ ffmpeg libheif-tools libwebp-tools exiftool python3 wget tar \
 && case "${TARGETARCH}" in \
      amd64) HUGO_ARCH=amd64 SWS_ARCH=x86_64-unknown-linux-musl SWS_SHA256=8f94abd9bc9c6d11240301d7271b95f9ec05b1b3e8509087c86ca8fd0b56fb4e ;; \
      arm64) HUGO_ARCH=arm64 SWS_ARCH=aarch64-unknown-linux-musl SWS_SHA256=28e53e5979735309ec3de685330719a11a0ef339aa06d0f0cd8eff5d973b9dfc ;; \
      *) echo "Unsupported TARGETARCH=${TARGETARCH}" >&2; exit 1 ;; \
    esac \
 && wget -q "https://github.com/gohugoio/hugo/releases/download/v${HUGO_VERSION}/hugo_extended_${HUGO_VERSION}_linux-${HUGO_ARCH}.tar.gz" -O /tmp/hugo.tar.gz \
 && tar -xzf /tmp/hugo.tar.gz -C /usr/local/bin hugo \
 && wget -q "https://github.com/static-web-server/static-web-server/releases/download/v${SWS_VERSION}/static-web-server-v${SWS_VERSION}-${SWS_ARCH}.tar.gz" -O /tmp/sws.tar.gz \
 && echo "${SWS_SHA256}  /tmp/sws.tar.gz" | sha256sum -c - \
 && mkdir -p /tmp/sws-extract \
 && tar -xzf /tmp/sws.tar.gz -C /tmp/sws-extract \
 && mv "/tmp/sws-extract/static-web-server-v${SWS_VERSION}-${SWS_ARCH}/static-web-server" /usr/local/bin/static-web-server \
 && rm -rf /tmp/sws-extract /tmp/hugo.tar.gz /tmp/sws.tar.gz \
 && chmod 0755 /usr/local/bin/hugo /usr/local/bin/static-web-server

WORKDIR /app
COPY sws.toml /etc/sws/sws.toml
COPY . /app
RUN chown -R 1000:1000 /app
ENV EXHIB_APP=/app \
    EXHIB_DATA=/data \
    SERVER_CONFIG_FILE=/etc/sws/sws.toml
USER 1000:1000
ENTRYPOINT ["python3", "entrypoint.py"]
