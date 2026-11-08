# Worker image: gallery source/templates plus Hugo, FFmpeg and metadata tools.
# Gallery media is never copied into this image; it lives on the PVC.
FROM alpine:3.22

ARG HUGO_VERSION=0.169.0
ARG TARGETARCH=amd64
RUN apk add --no-cache ca-certificates ffmpeg libheif-tools libwebp-tools exiftool python3 wget tar \
 && case "${TARGETARCH}" in \
      amd64) HUGO_ARCH=amd64 ;; \
      arm64) HUGO_ARCH=arm64 ;; \
      *) echo "Unsupported TARGETARCH=${TARGETARCH}" >&2; exit 1 ;; \
    esac \
 && wget -q "https://github.com/gohugoio/hugo/releases/download/v${HUGO_VERSION}/hugo_extended_${HUGO_VERSION}_linux-${HUGO_ARCH}.tar.gz" -O /tmp/hugo.tar.gz \
 && tar -xzf /tmp/hugo.tar.gz -C /usr/local/bin hugo \
 && rm -f /tmp/hugo.tar.gz \
 && chmod 0755 /usr/local/bin/hugo

WORKDIR /app
COPY . /app
RUN chown -R 1000:1000 /app
ENV EXHIB_APP=/app \
    EXHIB_DATA=/data
USER 1000:1000
ENTRYPOINT ["python3", "/app/processor/worker.py"]
