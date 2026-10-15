"""Anthropic SDK'sı maskele proxy'si üzerinden.

Önce:  maskele proxy --provider anthropic
Sonra: python examples/anthropic_sdk.py
"""

import anthropic

client = anthropic.Anthropic(base_url="http://127.0.0.1:8787")

log = open("examples/ornek.log", encoding="utf-8").read()

with client.messages.stream(
    model="claude-sonnet-4-5",
    max_tokens=800,
    messages=[{"role": "user", "content": f"Bu log'daki hatanın kök nedeni ne?\n\n{log}"}],
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
print()
