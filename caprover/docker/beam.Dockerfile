FROM mysql:8.0 AS mysql_client_stage

FROM php:8.4.19-fpm

ARG APP_NAME=Beam
ENV APP_NAME=${APP_NAME} \
    APP_ENV=staging \
    APP_DEBUG=false \
    FORCE_HTTPS=true \
    COMPOSER_ALLOW_SUPERUSER=1 \
    COMPOSER_HOME=/composer \
    YARN_CACHE_FOLDER=/yarn

ENV PATH=/composer/vendor/bin:/root/.yarn/bin:$PATH

ENV BUILD_DEPS="g++ build-essential libsasl2-dev libssl-dev" \
    RUN_DEPS="libzip-dev libicu-dev git curl unzip zlib1g-dev libpng-dev libjpeg-dev libonig-dev libncurses6 ca-certificates"

RUN apt-get update \
    && apt-get install -y --no-install-recommends $BUILD_DEPS $RUN_DEPS \
    && pecl install apcu \
    && docker-php-ext-enable apcu \
    && docker-php-ext-configure intl \
    && docker-php-ext-configure gd --with-jpeg=/usr/include/ \
    && docker-php-ext-install -j"$(nproc)" pdo_mysql bcmath mbstring zip intl sockets pcntl gd \
    && curl -fsSL https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install --global yarn@v2 \
    && apt-get purge -y --auto-remove $BUILD_DEPS \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /composer/cache /yarn /var/www/html

COPY --from=mysql_client_stage /usr/bin/mysqldump /usr/bin/mysqldump
COPY --from=mysql_client_stage /usr/bin/mysql /usr/bin/mysql
COPY Docker/php/log.conf /usr/local/etc/php-fpm.d/zz-log.conf
COPY caprover/scripts/php-entrypoint.sh /usr/local/bin/remp-caprover-entrypoint

WORKDIR /var/www/html
COPY Composer ./Composer
COPY Package ./Package
COPY Beam ./Beam

WORKDIR /var/www/html/Beam
RUN if [ -f composer.json ]; then composer install --no-dev --prefer-dist --no-interaction --optimize-autoloader; fi \
    && if [ -f package.json ]; then yarn install --immutable || yarn install; fi \
    && if [ -f package.json ]; then (yarn run production || yarn run prod || yarn run build || true); fi \
    && chmod +x /usr/local/bin/remp-caprover-entrypoint \
    && mkdir -p storage bootstrap/cache temp log \
    && chown -R www-data:www-data /var/www/html /composer /yarn

CMD ["/usr/local/bin/remp-caprover-entrypoint"]
