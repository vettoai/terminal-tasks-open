FROM python:3.11.11-slim-bookworm AS material
RUN pip install --no-cache-dir cryptography==44.0.2 cffi==1.17.1 pycparser==2.22
COPY fixture_material.py /build/fixture_material.py
COPY project/replay/customer_urls.csv /build/customer_urls.csv
RUN python /build/fixture_material.py /build/customer_urls.csv /assets

FROM python:3.11.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git vim-tiny procps openssl && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir requests==2.32.3 urllib3==2.2.3 certifi==2025.1.31 charset-normalizer==3.4.1 idna==3.10 pytest==8.3.5 iniconfig==2.0.0 packaging==24.2 pluggy==1.5.0 cryptography==44.0.2 cffi==1.17.1 pycparser==2.22
COPY project/ /srv/webhooks/
COPY --from=material /assets/ /srv/webhooks/local_ca/
WORKDIR /srv/webhooks
ENV PYTHONUNBUFFERED=1
