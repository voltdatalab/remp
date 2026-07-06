#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/var/www/html/${APP_NAME:?APP_NAME is required}"
cd "$APP_DIR"

if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
fi

# CapRover injects runtime configuration as environment variables. Keep .env as a
# fallback only; do not bake secrets into the image.
if [ "${REMP_RUN_MIGRATIONS:-false}" = "true" ]; then
  if [ -f artisan ]; then
    php artisan migrate --force
  elif [ -f bin/command.php ]; then
    php bin/command.php migrate:migrate --no-interaction
  fi
fi

if [ "${REMP_RUN_SEEDERS:-false}" = "true" ]; then
  if [ -f artisan ]; then
    php artisan db:seed --force
  elif [ -f bin/command.php ]; then
    php bin/command.php db:seed --no-interaction
  fi
fi

exec php-fpm
