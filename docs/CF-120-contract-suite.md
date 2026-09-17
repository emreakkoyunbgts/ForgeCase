# CF-120 — canlı HTTP sözleşme paketi

Kabul ölçütü (Backlog A124): *"The full contract-test suite passes against the live HTTP mesh
after cutover."* Bu belge paketin nasıl çalıştırılacağını, neyi kanıtladığını ve neyi
kanıtlamadığını anlatır. Tasarım gerekçeleri [CF-120 planı](CF-120-plan.md), bulguların
durumu [contract-findings.md](contract-findings.md) içindedir.

## Tek komut

17 Eylül 2026 doğrulaması: **240/240 canlı HTTP testi**, **573 varsayılan test** geçti.
Son rapor `out/acceptance/contract.json`; run ID `ae9ceba6306441d79f3f75360bdd2322`.
Kaynak hash'i güncel adayla eşleşiyor; eksik/fazla/skip/xfail/hata yok ve cleanup tam.
Bu çalışma ağacı PR'a hazırdır. `acceptance_ready=false` yalnız commit yapılmamış olmasından;
temiz aday kabulü için commit sonrasında aşağıdaki komut yeniden çalıştırılmalıdır.

```powershell
# Bir kez: Librarian embedding modelini önbelleğe indirir (koşu sırasında indirme yapılmaz).
.\.venv\Scripts\python.exe scripts/provision_librarian.py

# CF-120 kabul koşusu
.\.venv\Scripts\python.exe scripts/contract_mesh.py --output out/acceptance/contract.json
```

| Çıkış | Anlam |
|---|---|
| `0` | Envanterdeki bütün case'ler çalıştı ve geçti; önkoşul, provider trafiği ve cleanup tam |
| `2` | Başka her durum: kırmızı/skip/xfail case, eksik veya fazladan case, collection/teardown hatası, önkoşul hatası, kullanılmamış fault, cleanup hatası, koşu sırasında kaynak değişikliği, `--select` ile kısmi seçim |

Kabul için raporda ayrıca `acceptance_ready: true` gerekir. Bu yalnız **temiz (commit'lenmiş)
çalışma ağacında** mümkündür. Kirli ağaçta yapılan koşu geliştirme kanıtıdır.

## Ne çalışır

Runner (`scripts/contract_mesh.py`), `common.services` import edilmeden ortamı hazırlar ve
şunları başlatır:

- **Yedi gerçek API süreci:** Vault, Reader, Generator, Verifier, Publisher, Librarian ve
  Analyst, üretim giriş noktalarıyla (`scripts/run_mesh.py::APPS`) ve ayrı loopback portlarında.
- **Sentetik provider** (`contract/provider_stub.py`): yalnız dış LLM sınırı sentetiktir.
  `OPENAI_BASE_URL` sadece Generator ve Verifier'a verilir. Stub test edilen kodu import etmez;
  yalnız `contract/fixtures/cases.py` içindeki bağımsız metinlere cevap verir ve bilinmeyen
  içeriği reddeder.
- **Sınır relay'i** (`contract/boundary_relay.py`): servislerin Vault ve Verifier çağrıları
  buradan geçer. Relay her çağrıyı trace, method, status, idempotency key ve yetki eşleşmesiyle
  kaydeder; token değerini kaydetmez. Gecikme, 302, bozuk gövde veya sahte gate cevabı gibi
  fault'lar tek seferliktir ve yalnız ilgili trace'e uygulanır. Durdurulmuş bir bağımlılık
  tüketiciye uydurma bir HTTP status olarak değil, taşıma hatası olarak yansır.

Vault veritabanı ve Publisher artifact dizini koşuya özel geçici dizindedir; kullanıcının kalıcı
verisine dokunulmaz. Proxy değişkenleri temizlenir; model anahtarı yalnız sentetik stub içindir.

Testlerden önce **fonksiyonel hazırlık** yapılır. Reader ile yüklenen bir probe kaydı Librarian
`/search` ve `/match` üzerinden gerçek embedding ile bulunur, Analyst kaydı sayar, ardından kayıt
silinir ve yokluğu kontrol edilir. Model önbelleği yoksa koşu önkoşul hatasıyla durur; test skip
edilmez.

Pytest ayrı bir alt süreçte (`pytest contract`) çalışır. `contract/`, varsayılan
`pytest.ini testpaths` dışındadır: `python -m pytest -q` mesh başlatmaz. Paketi manifest olmadan
doğrudan çalıştırmak kullanım hatasıdır.

## Envanter

`contract/cases.json`, sürümlenmiş "tam paket" tanımıdır. Her nodeid için `owner`,
`requirement`, `boundary` ve tek satırlık `assertion` içerir. Runner toplanan case'leri bununla
karşılaştırır; eksik veya fazladan case koşuyu başarısız yapar. Varsayılan paketteki
`tests/test_cf120_inventory.py`, envanterin gerçek collection ile aynı kaldığını ve matris
kapsamını denetler.

Case ekledikten veya değiştirdikten sonra:

```powershell
.\.venv\Scripts\python.exe scripts/contract_mesh.py --freeze-inventory
git diff contract/cases.json   # değişikliği incelemeden commit'leme
```

| Dosya | Kapsam |
|---|---|
| `test_boundaries.py` | Vault roundtrip/ETag/If-Match/history/delete (F-01), tip doğrulama 422 (F-02), sonlu olmayan JSON değerleri ve auth; Reader upload, replay ve geçersiz belgeler |
| `test_gate.py` | Kaynak #1 × 7 poison × EN/DE/TR; hem `/verify` hem `/publish` reddi. Bozuk gate raporları, provider assessment ve translation hataları, format/layout reddi, görünür provenance'ta izin verilmeyen isim |
| `test_http_contracts.py` | Health/docs/OpenAPI, trace ve header sınırları, hop/log kanıtı, yetki aktarımı, yönlendirilmiş veya bozuk Vault cevapları, deprecated adapter'ların Vault otoritesi; altı içerik taşıyan serviste 422 yanıtının gönderilen içeriği yansıtmaması |
| `test_outages.py` | Gerçek Vault, Verifier, Librarian ve provider kesintileri; bağımlılık ve provider süre sınırları, 401/429 eşlemesi, Reader belirsiz/çelişkili depolama; başarısız son doğrulamada ve gecikmiş provider cevabında artifact oluşturulmaması |
| `test_pipeline.py` | 12 kaynak × EN/DE/TR = 36 temiz generate → PASS → publish → download; DOCX/PDF çıktıları, belge metni, provenance, provider aşamaları, final payload ve HTTP hop'ları; Workflow durum geçişleri ve açık isimlendirme izni |
| `test_retrieval_analytics.py` | `/search` ve `/match` (dense/hybrid), 12 kaynak coverage/gaps, boş corpus, gap çapraz çarpımı, 101 kayıtla sayfalama, eksik sayfanın 502 ile reddi, trailing slash (F-04) |

Güncel case sayısı `contract/cases.json` ve o adayın collection sonucundan okunur.
Önceki 215-case koşusunun kanıtı kendi kaynak sürümüne aittir; sonradan değişen
paketin geçtiğini göstermez. Bu kapsam tablosu bir başarı raporu değildir.

## Kanıt

Her koşu `out/acceptance/cf120/<run-id>/` altında `contract.json`, `pytest.json`, `junit.xml`,
`pytest.log`, `provider-calls.json`, `boundary-calls.json` ve `logs/<servis>.log` bırakır.
`--output` aynı raporun kopyasıdır; `live.json` adı reddedilir.

Desteklenen normal launcher da aynı `scripts/http_logging.json` dosyasını kullanır.
`python scripts/run_mesh.py --isolated` ile başlatılan servislerin correlation logları
`out/logs/` altındadır; contract koşusu kendi run dizinini kullanır.

| Alan | Anlam |
|---|---|
| `source.commit`, `working_tree_dirty`, `diff_sha256`, `files_sha256` | Aday kimliği. `files_sha256` koşu sonunda yeniden hesaplanır; değişmişse koşu başarısız olur |
| `environment` | Python, paket sürümleri, `fixture_sha256` |
| `mesh.health`, `mesh.functional_readiness`, `mesh.process_history` | Hazırlık ve bütün PID'ler |
| `selection` | Beklenen, toplanan, eksik ve fazladan case'ler; `developer_filter` |
| `execution_complete` | Bütün beklenen case'lerin raporu var (geçti anlamına gelmez) |
| `contract_conformant` | Hepsi geçti; eksik, skip, xfail veya hata yok |
| `acceptance_ready` | Conformant ve temiz ağaç |
| `release_eligible` | Sentetik provider koşusunda **her zaman false** |
| `results[]`, `failures[]` | nodeid, faz, durum/neden, owner/requirement/boundary, servisler ve istek trace kimlikleri; trace kayıtlarında yalnız servis/kimlik tutulur |
| `cleanup` | Yeniden başlatılanlar dahil her sahip olunan süreç çıktı mı, dinleyiciler kapandı mı |

## Geliştirici döngüsü

```powershell
.\.venv\Scripts\python.exe scripts/contract_mesh.py --output out/acceptance/contract-dev.json --select "test_gate"
```

`--select` bir pytest `-k` ifadesidir. Kısmi seçim her zaman exit `2` ve
`contract_conformant: false` üretir. Koşu sırasında `contract/`, servis kodu, `tests/` veya
`docs/openapi/` düzenlenirse rapor geçersiz sayılır.

## Bu paket neyi kanıtlamaz

- **Gerçek model kalitesini.** Sentetik provider'ın çeviri ve assessment cevapları fixture'dır.
  Olumsuz provider kararının yayını durdurduğu kanıtlanır; gerçek modelin o hatayı yakaladığı
  kanıtlanmaz. Gerçek model kabulü ayrıca `scripts/live_acceptance.py` ile yapılır.
- İki UI'ı, görsel belge incelemesini (taşma, uzun Almanca metin) ve release tag kararını.
- Genel exactly-once teslimi: `Idempotency-Key` yalnız taşınır.
- CF-88 olumlu bağlam davranışını (F-12).

## Sorun giderme

| Belirti | Neden / çözüm |
|---|---|
| `Librarian functional readiness failed ... provision` | `scripts/provision_librarian.py` çalıştırılmamış |
| `<servis> exited during startup` + log kuyruğu | Import veya konfigürasyon hatası; `out/acceptance/cf120/<run-id>/logs/<servis>.log` |
| `Missing provider traffic or armed-but-unused faults` | Bir test fault kurdu ama sınıra hiç ulaşmadı; sahte yeşil engellendi |
| `source changed during the run` | Koşu sırasında dosya değişti (editör, başka ajan); temiz ağaçta yeniden çalıştır |
| `Readiness deadline` | Port çakışması veya çok yavaş açılış; runner port haritasını üç kez yeniden dener |
