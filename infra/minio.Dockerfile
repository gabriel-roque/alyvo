FROM golang:1.24-alpine AS build

RUN go install github.com/minio/minio@RELEASE.2025-10-15T17-29-55Z

FROM alpine:3.22

RUN apk add --no-cache ca-certificates curl \
    && addgroup -S minio \
    && adduser -S -G minio minio \
    && mkdir -p /data \
    && chown minio:minio /data
COPY --from=build /go/bin/minio /usr/local/bin/minio
USER minio
ENTRYPOINT ["minio"]
