"""maskele'yi kütüphane olarak kullanmak: kendi LLM çağrını sar."""

from maskele import Masker, VaultStore, load_config
from maskele.vault import vault_path

cfg = load_config()  # .maskele.toml varsa okunur
store = VaultStore(vault_path("ornek"), ttl_hours=cfg.vault_ttl_hours)
masker = Masker(store.load(), config=cfg)

text = open("examples/ornek.log", encoding="utf-8").read()
result = masker.mask(text)
store.save(masker.vault)

print("Modele giden metin:\n", result.text)
print("Maskelenenler:", dict(result.counts))

# reply = senin_llm_cagrin(result.text)
reply = "[[IP_2]] üzerindeki servis [[IP_3]] veritabanına bağlanamıyor; [[NAME_1]] etkilendi."
print("\nGeri çevrilmiş cevap:\n", masker.unmask(reply).text)

# Akış (streaming) cevaplar için:
s = masker.stream()
for part in ["[[IP", "_2]] çöktü, ", "IP_3 sağlam"]:
    print(s.feed(part), end="")
print(s.flush())
