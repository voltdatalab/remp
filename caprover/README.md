# REMP on CapRover — Núcleo staging adaptation

This directory contains the first-pass CapRover adaptation for evaluating `remp2020/remp` inside the Núcleo/VoltDataLab infrastructure **before any definitive deploy**.

## Status

- Target pattern: one CapRover app per container/service, using the `st-` staging prefix.
- No production secrets are committed.
- No CapRover app is created by this repository alone; deployment still needs explicit operator approval and dashboard/API configuration.
- The original `docker-compose.yml` remains available for upstream/dev comparison, but CapRover should use the `caprover/apps/*/captain-definition` files.

## App matrix

| CapRover app | Captain definition | Public? | Notes |
|---|---|---:|---|
| `st-remp-nginx` | `caprover/apps/st-remp-nginx/captain-definition` | yes, protected | Edge router for the REMP UI hostnames. Set Container HTTP Port `80`. |
| `st-remp-beam` | `caprover/apps/st-remp-beam/captain-definition` | no | PHP-FPM for Beam. |
| `st-remp-campaign` | `caprover/apps/st-remp-campaign/captain-definition` | no | PHP-FPM for Campaign. |
| `st-remp-mailer` | `caprover/apps/st-remp-mailer/captain-definition` | no | PHP-FPM for Mailer. Use Mailhog in POC. |
| `st-remp-sso` | `caprover/apps/st-remp-sso/captain-definition` | no/limited | PHP-FPM for SSO. |
| `st-remp-tracker` | `caprover/apps/st-remp-tracker/captain-definition` | optional | Go tracker API, only expose if testing collection. |
| `st-remp-segments` | `caprover/apps/st-remp-segments/captain-definition` | no | Go segments API. |
| `st-remp-mysql` | `caprover/apps/st-remp-mysql/captain-definition` | no | Uses official `mysql:8.0`; needs persistent volume `/var/lib/mysql`, strong `MYSQL_ROOT_PASSWORD`, and manual bootstrap SQL. |
| `st-remp-redis` | `caprover/apps/st-remp-redis/captain-definition` | no | Needs persistent volume `/data` if state persistence is desired. |
| `st-remp-elasticsearch` | `caprover/apps/st-remp-elasticsearch/captain-definition` | no | Needs persistent volume `/usr/share/elasticsearch/data`; do not expose directly. |
| `st-remp-zookeeper` | `caprover/apps/st-remp-zookeeper/captain-definition` | no | Internal Kafka dependency. |
| `st-remp-kafka` | `caprover/apps/st-remp-kafka/captain-definition` | no | Internal broker. Use internal hostname in env. |
| `st-remp-telegraf` | `caprover/apps/st-remp-telegraf/captain-definition` | no | Kafka → Elasticsearch consumer. |
| `st-remp-mailhog` | `caprover/apps/st-remp-mailhog/captain-definition` | no/temporary | Only for POC mail capture. |
| `st-remp-kibana` | `caprover/apps/st-remp-kibana/captain-definition` | no/temporary | If exposed, protect with VPN/basic auth. |

## Important CapRover notes

1. CapRover internal service hostnames use `srv-captain--<app-name>`.
2. For GitHub Method 3, set the captain definition relative path per app, e.g. `caprover/apps/st-remp-beam/captain-definition`.
3. Do not expose MySQL, Redis, Kafka, Zookeeper, Elasticsearch, Adminer, Mailhog, or Kibana publicly without explicit protection.
4. Keep deployment branch isolated (`caprover/nucleo-staging`) until the team approves a final deployment model.
5. The PHP entrypoint supports optional migrations via `REMP_RUN_MIGRATIONS=true`; keep it `false` until database credentials, backups and rollback are defined.
6. The MySQL app intentionally uses the official `mysql:8.0` image. After the database app is running, bootstrap the required REMP databases manually with `caprover/bootstrap/mysql-init.sql` instead of maintaining a custom MySQL image.

## Manual MySQL bootstrap

After creating `st-remp-mysql` with the official image and a persistent `/var/lib/mysql` volume, run the SQL in:

```txt
caprover/bootstrap/mysql-init.sql
```

The script only creates the required databases:

- `beam`
- `campaign`
- `mailer`
- `sso`

Do not commit real MySQL passwords or user credentials. Keep those in CapRover env vars / operational notes.

## Required env adjustments for staging

Use `caprover/env/staging.example.env` as a starting point and override per app in CapRover. At minimum:

- `APP_ENV=staging`
- `APP_DEBUG=false`
- `FORCE_HTTPS=true`
- `DB_HOST=srv-captain--st-remp-mysql`
- `REDIS_HOST=srv-captain--st-remp-redis`
- strong, unique database password
- real `APP_KEY`/JWT/SSO secrets generated in CapRover, never committed

For Go services:

- `TRACKER_MYSQL_ADDR=srv-captain--st-remp-mysql:3306`
- `TRACKER_BROKER_ADDRS=srv-captain--st-remp-kafka:9092`
- `SEGMENTS_MYSQL_ADDR=srv-captain--st-remp-mysql:3306`
- `SEGMENTS_ELASTIC_ADDRS=http://srv-captain--st-remp-elasticsearch:9200`

For Kafka:

- `KAFKA_ZOOKEEPER_CONNECT=srv-captain--st-remp-zookeeper:2181`
- `KAFKA_ADVERTISED_HOST_NAME=srv-captain--st-remp-kafka`
- `KAFKA_CREATE_TOPICS=beam_events:1:1`

## Open risks before deploy

- The upstream project is compose/dev-oriented. This branch removes bind-mount assumptions, but full runtime validation still requires a protected CapRover staging deployment.
- PHP asset builds may need app-specific production commands; the Dockerfiles try common `yarn` production/build commands and do not fail if none exist.
- Elasticsearch remains configured without xpack security because it is expected to be internal-only in this POC.
- OAuth/callback URLs, SSO API tokens, JWT secrets and app keys must be designed before exposing any UI.
