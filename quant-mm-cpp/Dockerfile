FROM gcc:14 AS build
WORKDIR /app
COPY . .
RUN cmake -B build -S . && cmake --build build -j

FROM debian:bookworm-slim
COPY --from=build /app/build/quant-mm /usr/local/bin/quant-mm
ENTRYPOINT ["quant-mm"]
