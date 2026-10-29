ARG PYTHON_BASE=python:3.11-slim-bookworm@sha256:90d117a7f1ef6535dc75831e1a9184725757fede0d4d424d7977fb5429d50610

FROM ${PYTHON_BASE} AS verifier-base
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates g++ git iverilog make perl procps yosys zlib1g-dev \
    && find /var/lib/apt/lists -type f -delete
COPY requirements.txt /tmp/requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --no-cache-dir -r /tmp/requirements.txt

FROM verifier-base AS verilator-build
ARG VERILATOR_VERSION=5.036
ARG VERILATOR_SHA256=4199964882d56cf6a19ce80c6a297ebe3b0c35ea81106cd4f722342594337c47
ARG VERILATOR_URL=https://github.com/verilator/verilator/archive/refs/tags/v5.036.tar.gz
RUN apt-get update \
    && apt-get install -y --no-install-recommends autoconf bison curl flex help2man \
    && find /var/lib/apt/lists -type f -delete
RUN apt-get update \
    && apt-get install -y --no-install-recommends libfl-dev \
    && find /var/lib/apt/lists -type f -delete
RUN --mount=type=cache,id=uart-verilator-5.036,target=/tmp/verilator-5.036 \
    test -n "${VERILATOR_SHA256}" \
    && curl --fail --location --retry 3 \
        "${VERILATOR_URL}" \
        --output /tmp/verilator.tar.gz \
    && printf '%s  %s\n' "${VERILATOR_SHA256}" /tmp/verilator.tar.gz | sha256sum --check \
    && tar -xzf /tmp/verilator.tar.gz -C /tmp \
    && cd "/tmp/verilator-${VERILATOR_VERSION}" \
    && autoconf \
    && ./configure --prefix=/opt/verilator \
    && make -j4 \
    && make install

FROM verifier-base AS runtime
COPY --from=verilator-build /opt/verilator /opt/verilator
LABEL io.uart.python-base="python:3.11-slim-bookworm@sha256:90d117a7f1ef6535dc75831e1a9184725757fede0d4d424d7977fb5429d50610" \
      io.uart.verilator-version="5.036" \
      io.uart.verilator-source-sha256="4199964882d56cf6a19ce80c6a297ebe3b0c35ea81106cd4f722342594337c47"
ENV PATH="/opt/venv/bin:/opt/verilator/bin:${PATH}" \
    PYTHON="/opt/venv/bin/python"
RUN useradd --create-home --uid 1000 --shell /bin/bash uart \
    && install -d -o uart -g uart /workspace /opt/uart-toolchain \
    && dpkg-query -W -f='${binary:Package}\t${Version}\n' > /opt/uart-toolchain/apt-packages.tsv \
    && /opt/venv/bin/python -m pip freeze > /opt/uart-toolchain/python-packages.txt \
    && python --version > /opt/uart-toolchain/python-version.txt \
    && verilator --version > /opt/uart-toolchain/verilator-version.txt
WORKDIR /workspace
USER uart
CMD ["make", "demo", "PYTHON=/opt/venv/bin/python"]
