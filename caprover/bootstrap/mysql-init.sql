-- Manual MySQL bootstrap for the REMP CapRover staging POC.
-- Run once against the `st-remp-mysql` database after creating the app with
-- the official `mysql:8.0` image and a persistent `/var/lib/mysql` volume.
--
-- This script intentionally creates databases only. Credentials, users and
-- passwords should be managed in CapRover env vars / operational runbooks, not
-- committed to the repository.

CREATE DATABASE IF NOT EXISTS beam COLLATE 'utf8mb4_unicode_ci';
CREATE DATABASE IF NOT EXISTS campaign COLLATE 'utf8mb4_unicode_ci';
CREATE DATABASE IF NOT EXISTS mailer COLLATE 'utf8mb4_unicode_ci';
CREATE DATABASE IF NOT EXISTS sso COLLATE 'utf8mb4_unicode_ci';
