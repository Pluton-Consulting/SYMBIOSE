# Image Caddy personnalisée : Caddy + module DNS Gandi (pour le challenge ACME DNS-01).
# Le challenge DNS-01 permet d'obtenir un certificat Let's Encrypt VALIDE pour un service
# qui n'est PAS joignable publiquement (ici l'app est sur une IP privée du VPN).
# Le DNS de pluton-consulting.fr est géré par Gandi (LiveDNS) → module caddy-dns/gandi.
FROM caddy:2.8-builder AS builder
RUN xcaddy build --with github.com/caddy-dns/gandi

FROM caddy:2.8
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
