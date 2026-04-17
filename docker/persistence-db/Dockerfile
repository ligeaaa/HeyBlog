FROM postgres:16

ARG AGE_VERSION=release/PG16/1.6.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        flex \
        bison \
        git \
        postgresql-server-dev-16 \
    && git clone --depth 1 --branch "${AGE_VERSION}" https://github.com/apache/age.git /tmp/age \
    && make -C /tmp/age PG_CONFIG=/usr/lib/postgresql/16/bin/pg_config install \
    && rm -rf /tmp/age \
    && apt-get purge -y git \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*
