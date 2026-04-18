FROM postgres:16

ARG AGE_VERSION=release/PG16/1.6.0

RUN sed -i "s|http://deb.debian.org/debian|http://mirrors.tuna.tsinghua.edu.cn/debian|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::http::Pipeline-Depth=0 update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        flex \
        bison \
        postgresql-server-dev-16 \
    && mkdir -p /tmp/age \
    && curl -fsSL --retry 5 --retry-all-errors --retry-delay 2 "https://codeload.github.com/apache/age/tar.gz/refs/heads/${AGE_VERSION}" -o /tmp/age.tar.gz \
    && tar -xzf /tmp/age.tar.gz --strip-components=1 -C /tmp/age \
    && make -C /tmp/age PG_CONFIG=/usr/lib/postgresql/16/bin/pg_config install \
    && rm -rf /tmp/age /tmp/age.tar.gz \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*
