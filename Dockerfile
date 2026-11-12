# VeriPilot development environment: Ubuntu 22.04 (Python 3.10) + Verilator 5.034
FROM ubuntu:22.04

ARG VERILATOR_TAG=v5.034
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
      git ca-certificates build-essential autoconf flex bison help2man perl \
      python3 python3-venv python3-pip python3-dev \
      libfl2 libfl-dev zlib1g-dev ccache make g++ \
    && rm -rf /var/lib/apt/lists/*

# Verilator is built from source because apt does not ship 5.034
RUN git clone --depth 1 --branch ${VERILATOR_TAG} https://github.com/verilator/verilator /tmp/verilator \
    && cd /tmp/verilator && autoconf && ./configure && make -j"$(nproc)" && make install \
    && rm -rf /tmp/verilator

WORKDIR /workspace
CMD ["bash"]
