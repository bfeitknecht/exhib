# SWS serving image for the exhib gallery. Same upstream image and version
# the infra deployment used, with the configuration baked in so the infra
# repo needs no sws.toml, no ConfigMap and no volume.
FROM joseluisq/static-web-server:2.44.1-alpine

COPY sws.toml /etc/sws/sws.toml

ENV SERVER_CONFIG_FILE=/etc/sws/sws.toml
