# maskele proxy'si, konteyner içinde.
#
#   docker build -t maskele .
#   export MASKELE_PROXY_KEY=$(openssl rand -hex 24)
#   docker run --rm -p 127.0.0.1:8787:8787 -e MASKELE_PROXY_KEY maskele --provider openai
#
# Uygulamanızda:
#   OpenAI(base_url="http://localhost:8787/v1",
#          default_headers={"X-Maskele-Key": os.environ["MASKELE_PROXY_KEY"]})
#
# Konteyner içinde 0.0.0.0'a bağlanmak gerektiği için erişim anahtarı zorunludur.
# Proxy kalıcı kasa tutmaz: her istek kendi bellek içi kasasıyla işlenir.
FROM python:3.12-slim

RUN useradd --create-home --uid 10001 maskele \
 && mkdir -p /data && chown maskele:maskele /data && chmod 700 /data
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY maskele ./maskele
RUN pip install --no-cache-dir ".[crypto]"

USER maskele
ENV MASKELE_HOME=/data MASKELE_NO_CONFIG=1 PYTHONUNBUFFERED=1
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,os;urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8787/maskele/health',headers={'Host':'127.0.0.1:8787','X-Maskele-Key':os.environ.get('MASKELE_PROXY_KEY','')}),timeout=2)" || exit 1

# --no-tls: konteyner portu YALNIZCA 127.0.0.1'e yayınlanmalı (-p 127.0.0.1:8787:8787). Ağ
# üzerinden erişim gerekiyorsa önüne TLS sonlandıran bir ters proxy koyun (README: Caddy örneği).
ENTRYPOINT ["maskele", "proxy", "--host", "0.0.0.0", "--port", "8787", "--access-key-env", "MASKELE_PROXY_KEY", "--no-tls"]
CMD ["--provider", "openai"]
