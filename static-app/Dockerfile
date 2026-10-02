# One image for every static app in this collection: the upstream index.html,
# served by nginx on the add-on's ingress port. The sync workflow fetches the
# index.html of the commit it builds next to this file and passes the rest as
# build arguments.
ARG BUILD_FROM
FROM ${BUILD_FROM}

ARG PORT
ARG BUILD_ARCH
ARG BUILD_VERSION

RUN apk add --no-cache nginx \
 && printf 'server {\n  listen %s;\n  root /www;\n  index index.html;\n  add_header Cache-Control "no-cache";\n}\n' "${PORT}" \
    > /etc/nginx/http.d/default.conf

COPY index.html /www/index.html

LABEL io.hass.type="addon" \
      io.hass.arch="${BUILD_ARCH}" \
      io.hass.version="${BUILD_VERSION}"

EXPOSE ${PORT}
ENTRYPOINT []
CMD ["nginx", "-g", "daemon off;"]
