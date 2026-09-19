FROM python:3.13-slim AS build

WORKDIR /build
COPY pyproject.toml ./
COPY src ./src
RUN python -m pip wheel --no-cache-dir --no-deps --wheel-dir /wheels .

FROM python:3.13-slim

RUN useradd --create-home --uid 10001 tracker
COPY --from=build /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

USER 10001:10001
EXPOSE 39001/udp
EXPOSE 8080/tcp
ENTRYPOINT ["open-sail-tracker-backend"]
CMD ["--port", "39001"]
