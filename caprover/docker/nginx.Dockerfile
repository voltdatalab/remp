FROM nginx:stable

RUN apt-get update \
    && apt-get install -y --no-install-recommends gettext-base ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /var/www/html
COPY Beam/public ./Beam/public
COPY Campaign/public ./Campaign/public
COPY Mailer/www ./Mailer/www
COPY Sso/public ./Sso/public
COPY Docker/adminer ./Docker/adminer
COPY caprover/nginx/remp-caprover.conf.template /etc/nginx/templates/remp-caprover.conf.template

ENV NGINX_PORT=80 \
    CAMPAIGN_FPM=srv-captain--st-remp-campaign:9000 \
    MAILER_FPM=srv-captain--st-remp-mailer:9000 \
    BEAM_FPM=srv-captain--st-remp-beam:9000 \
    SSO_FPM=srv-captain--st-remp-sso:9000 \
    TRACKER_UPSTREAM=srv-captain--st-remp-tracker:8081 \
    SEGMENTS_UPSTREAM=srv-captain--st-remp-segments:8082 \
    MAILHOG_UPSTREAM=srv-captain--st-remp-mailhog:8025 \
    KIBANA_UPSTREAM=srv-captain--st-remp-kibana:5601

CMD ["/bin/sh", "-c", "envsubst '$$NGINX_PORT $$CAMPAIGN_FPM $$MAILER_FPM $$BEAM_FPM $$SSO_FPM $$TRACKER_UPSTREAM $$SEGMENTS_UPSTREAM $$MAILHOG_UPSTREAM $$KIBANA_UPSTREAM' < /etc/nginx/templates/remp-caprover.conf.template > /etc/nginx/conf.d/default.conf && exec nginx -g 'daemon off;'"]
