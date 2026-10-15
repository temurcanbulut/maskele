import os
import sys
from pathlib import Path

# Testler kullanıcının kendi yapılandırma dosyalarından etkilenmesin
os.environ["MASKELE_NO_CONFIG"] = "1"
for k in ("MASKELE_PASSWORD", "MASKELE_SESSION"):
    os.environ.pop(k, None)
# Yerel sahte sunuculara giden istekler kurumsal proxy'ye gitmesin
os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"

# Test modülleri birbirinin yardımcılarını içe aktarabilsin
sys.path.insert(0, str(Path(__file__).resolve().parent))
