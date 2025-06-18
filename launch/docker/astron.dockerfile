FROM ubuntu:22.04

# Install Astron Dependencies
RUN apt-get update && apt-get upgrade -y
RUN apt-get install -y \
    curl \
    cmake \
    build-essential \
    git \
    libboost-dev \
    libyaml-cpp-dev \
    libuv1-dev \
    libssl-dev \
    libsasl2-dev \
    ca-certificates

# Install C++ MongoDB driver so astron builds with Mongo.
WORKDIR /tmp
RUN curl -OL https://github.com/mongodb/mongo-cxx-driver/releases/download/r4.1.0/mongo-cxx-driver-r4.1.0.tar.gz && \
    tar -xzf mongo-cxx-driver-r4.1.0.tar.gz && \
    cd mongo-cxx-driver-r4.1.0/build && \
    cmake .. -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local && \
    cmake --build . --target install -- -j$(nproc)

# Set an ENV var for Astron to detect any drivers we installed previously.
ENV CMAKE_PREFIX_PATH=/usr/local/lib/cmake

# Build Astron
WORKDIR /app/build
RUN git clone https://github.com/ranked-toontown/Astron.git .
RUN mkdir -p build && \
    cd build && \
    cmake .. -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_PREFIX_PATH=/usr/local/lib/cmake && \
    cmake --build .

# Allow Astron to detect shared libraries during runtime. Without this, Astron will not be able to find certain .so files.
ENV LD_LIBRARY_PATH=/usr/local/lib

# Start Astron
WORKDIR /app/game/astron
ENTRYPOINT [ "/app/build/build/astrond", "config/astrond.yml" ]
