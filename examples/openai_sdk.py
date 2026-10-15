"""OpenAI SDK'sı maskele proxy'si üzerinden.

Önce:  maskele proxy --provider openai
Sonra: python examples/openai_sdk.py

Kodda değişen tek şey base_url. API anahtarı olduğu gibi OpenAI'ye iletilir;
log'daki IP, e-posta ve TCKN ise makineden hiç çıkmaz.
"""

from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8787/v1")

log = open("examples/ornek.log", encoding="utf-8").read()

stream = client.chat.completions.create(
    model="gpt-4o-mini",
    stream=True,
    messages=[
        {"role": "system", "content": "Sen deneyimli bir SRE'sin. Kısa ve net ol."},
        {"role": "user", "content": f"Bu log'daki hatanın kök nedeni ne?\n\n{log}"},
    ],
)
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="", flush=True)
print()
