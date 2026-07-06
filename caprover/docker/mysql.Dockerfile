FROM mysql:8.0
COPY Docker/mysql/init.sql /docker-entrypoint-initdb.d/init.sql
CMD ["--character-set-server=utf8mb4", "--collation-server=utf8mb4_unicode_ci", "--skip-character-set-client-handshake", "--explicit_defaults_for_timestamp"]
