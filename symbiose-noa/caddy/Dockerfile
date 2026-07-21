# Image Caddy personnalisée : Caddy + module DNS OVH (pour le challenge ACME DNS-01).
# Le challenge DNS-01 permet d'obtenir un certificat Let's Encrypt VALIDE pour un service
# qui n'est PAS joignable publiquement (ici l'app est sur une IP privée du VPN).
FROM caddy:2.8-builder AS builder
RUN xcaddy build --with github.com/caddy-dns/ovh

FROM caddy:2.8
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
