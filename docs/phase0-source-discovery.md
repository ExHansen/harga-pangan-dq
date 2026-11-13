# Phase 0 — Data source discovery

Researched on 2026-11-12 (Thursday). Method: public pages, robots.txt, the FAQ, and
13 manual GET requests to `bi.go.id` spaced at least 2 s apart, from a non-Indonesian IP.
Raw sample responses are in [`phase0/samples/`](phase0/samples/). No pipeline code was written.

## Recommendation in one paragraph

Use **PIHPS Nasional (Bank Indonesia)** as the only automated source. Read it through the same
public, unauthenticated JSON endpoints that its own "Tabel Harga" pages call, once per business day.
One request per commodity returns every province plus the national average, so a full day costs
**21 requests** for traditional markets. Do **not** automate Panel Harga Pangan (Badan Pangan
Nasional). Its panel and API hosts were unreachable from outside Indonesia, which includes
GitHub-hosted runners. Its open-data portal disallows `/api/` and `/download/` in robots.txt and is
behind reCAPTCHA. Under the brief's rule ("if a source does not allow automated access, do not use
it"), it is out. Check #7 (cross-source reconciliation) is replaced by reconciliation *within*
PIHPS, unless you approve exploring a second source.

## Side-by-side

| | **PIHPS Nasional** (Bank Indonesia) | **Panel Harga Pangan** (Badan Pangan Nasional) |
|---|---|---|
| URL | https://www.bi.go.id/hargapangan (the old `hargapangan.id` returns HTTP 521) | https://panelharga.badanpangan.go.id |
| Commodities | 10 groups, 21 items: rice ×6 grades, chicken, beef ×2, eggs, shallot, garlic, red chilli ×2, bird's-eye chilli ×2, cooking oil ×3, sugar ×2 | Per launch coverage: rice, shallot, chilli, beef, chicken, eggs, sugar, oil, corn, soybean, live cattle and others. *Not verified at source.* |
| Geography | 34 provinces (pre-2022 list) → regency/city → market. The FAQ says 82 sample cities (the BPS CPI cities), but the live reference list also contains Mimika, Nabire and Jayawijaya, so the FAQ is probably out of date. | National, province, regency/city (per press coverage) |
| Market types | Traditional market, modern market, wholesaler (*pedagang besar*), producer | Producer and consumer levels |
| Collection & publication | Enumeration on weekdays 09:00–11:00 WIB. Updates every 2 h from 10:00 to 13:00 WIB, with a publication target of **13:00 WIB**. **Revisions are possible until the next day.** No weekend data (7–8 Nov 2026 absent in samples). | Described as "real-time", entered by enumerators. *Not verified.* |
| History | Data returned for January 2018. January 2017 returned an empty result. The exact start is still to be pinned down (M6). | Unknown (unreachable) |
| Access | No documented API and no bulk download. The UI has a client-side Excel export of the visible grid. The page's own JSON endpoints are public GETs: `GetGridDataKomoditas`, `GetGridDataDaerah`, `GetRef*`. There is also a mobile app. | Panel and `api-panelhargav2.badanpangan.go.id`: **connection refused or timed out** from here, while `bi.go.id` worked from the same machine. The open-data portal `data.badanpangan.go.id` is reachable, but only has **monthly** datasets, uses reCAPTCHA, and its robots.txt disallows `/api/` and `/download/`. |
| robots.txt | `User-agent: *` / `Allow: /`. It disallows only SharePoint paths (`/_layouts`, `/Lists`, …). `/hargapangan/` is allowed. | Panel: could not be read. Open-data portal: disallows `/api/`, `/download/`, `/dashboard`. |
| Terms / licence | No terms-of-use page and no open licence. The footer says "Hak Cipta © 2022 PIHPS Nasional - Semua Hak Dilindungi". The privacy policy says the site is owned by Bank Indonesia and that device data is collected automatically "to identify possible misuse". | The data.go.id listing has no licence and is marked "Terbatas" (restricted). |
| Citation | None prescribed. Proposed: *"Sumber: Pusat Informasi Harga Pangan Strategis (PIHPS) Nasional, Bank Indonesia — bi.go.id/hargapangan, diakses <tanggal>."* | — |

## Legal position (my reading, not legal advice)

- PIHPS has **no open licence**, and the footer reserves all rights.
- **UU 28/2014 Pasal 44(1)(a)** says that using or reproducing a work is not infringement *"jika
  sumbernya disebutkan atau dicantumkan secara lengkap"* for education, research, scientific writing,
  reports, or critique, *"dengan tidak merugikan kepentingan yang wajar"* of the rights holder.
  A non-commercial portfolio project with an analysis write-up fits this best.
- Pasal 43(b) (works made by or on behalf of the government) excludes works carrying a statement that
  they are protected. The footer is such a statement, so the project should not rely on 43(b).
- Rules this implies for the design:
  1. Non-commercial use only.
  2. Full citation on every dashboard page and in the README.
  3. Publish derived data (province averages, changes, data-quality status) rather than a bulk
     re-download of the raw archive. Where the raw archive lives is a design decision for the next
     phase.
  4. Label the site "not an official statistic".
- Optional: email `bicara@bi.go.id` (BI's contact centre, named in the privacy policy) to describe the
  project and ask for written confirmation. Your call.

## Findings that shape the design

1. **Wide, string-typed payload.** Dates are column keys (`"12/11/2026"`, dd/mm/yyyy). Prices are
   strings with comma thousand separators (`"16,500"`). A missing value is `"-"`. Rows carry a `level`:
   0 = national (`"Semua Provinsi"`), 1 = province. In the by-commodity view, provinces are identified
   **by name only**, with no id, so the province reference table must map name → id.
2. **Not every province reports every commodity.** Cabai Merah Besar on 10–12 Nov 2026 had 27 of 34
   provinces. Sumatera Utara, Sumatera Barat, Kepulauan Riau, Bangka Belitung, Gorontalo, Sulawesi
   Utara and Maluku were absent. The "expected combinations" for the completeness check must be learned
   from history; they cannot be assumed to be 34 × 21.
3. **Late data is normal.** At 17:24 WIB on 12 Nov, Kalimantan Barat still showed `"-"` for that day,
   and the FAQ allows revisions until the next day. Each run should therefore re-fetch D-1 (and D-2),
   and the raw store keeps every fetch as a separate snapshot.
4. **Unit metadata disagrees with the FAQ.** `GetRefCommodityAndCategory` returns `denomination: "kg"`
   for every item, including cooking oil. The FAQ says cooking oil is per **litre**. This is a real
   data-quality issue to document and test.
5. **The 34 → 38 province mapping can be resolved at city level.** The sample cities in old *Papua*
   are Kota Jayapura (now Papua), Kab. Jayawijaya (Papua Pegunungan), Kab. Merauke (Papua Selatan), and
   Kab. Mimika and Kab. Nabire (Papua Tengah). The cities in old *Papua Barat* are Kab. Manokwari (Papua
   Barat) and Kota Sorong (Papua Barat Daya). There are two options for the design phase:
   - **A:** keep the source's 34 provinces and document the one-to-many mapping to 38;
   - **B:** fetch city-level rows (same request, `showKota=true`) and re-aggregate to all 38 provinces.
6. **Bot protection is present but not blocking.** Responses set an F5-style `TS01…` cookie. Cookie-less
   requests from a US IP succeeded. The risk is that datacenter IPs get blocked later. The freshness and
   schema-drift checks will surface that.
7. **There is a business calendar.** Weekends have no data, and public holidays presumably have none
   either. The freshness check needs an Indonesian business-day calendar that includes *cuti bersama*.
8. **The endpoints are undocumented**, so they can change without notice. This is why the schema-drift
   check and recorded fixtures matter.
9. **Volume:**
   - a daily run is 21 requests (traditional markets) or 84 (all four market types);
   - backfill from 2018 to today is about 8.8 years. With one request per commodity per quarter,
     that is about 750 requests, throttled and spread over several nights.
   - *Correction (M2):* long windows are expensive for the source. A one-year window timed out
     (> 30 s), while a month takes ~5 s. Backfill therefore uses monthly windows, about 2,160
     requests for 2018 → mid-2026 (see design.md §2, Backfill).

## Proposed access rules for PIHPS

- Endpoint: `GET /hargapangan/WebSite/TabelHarga/GetGridDataKomoditas` with `price_type_id`,
  `comcat_id`, `tipe_laporan=1` (daily), `start_date` and `end_date`.
- At most 1 request every 3 s. Retry at most 3 times with backoff. Stop on 403 or 429.
- One scheduled run per business day, after the 13:00 WIB publication target, plus one late retry
  window. Each run re-fetches D-1 and D-2 for revisions.
- Each raw response is stored once (gzipped, date-partitioned, with a content hash). Re-running a day
  with an unchanged response writes nothing.
- User-Agent: `harga-pangan-dq/<version> (+https://github.com/ExHansen/harga-pangan-dq)`.
- Runs on GitHub-hosted runners. A US IP worked during this research.

## Second source / check #7

There is **no second automated source** for now. Check #7 instead becomes reconciliation within PIHPS:

- the national row compared with the mean of the provinces. These are computed differently (the FAQ
  says the national figure averages all traders), so the check uses a tolerance band, not equality;
- traditional-market prices compared with modern-market prices for the same commodity and province.

An option that needs your approval: BPS monthly consumer prices through its WebAPI (a free key) as a
monthly cross-check. I have not researched its terms yet.

## Sources

- PIHPS home: https://www.bi.go.id/hargapangan
- PIHPS FAQ: https://www.bi.go.id/hargapangan/Informasi/FAQ
- PIHPS privacy policy: https://www.bi.go.id/hargapangan/PrivacyPolicy
- BI robots.txt: https://www.bi.go.id/robots.txt
- Bapanas open-data portal: https://data.badanpangan.go.id (robots.txt at `/robots.txt`)
- data.go.id listing (Bapanas, monthly): https://data.go.id/dataset/dataset/rata-rata-harga-pangan-bulanan-tingkat-konsumen-provinsi-update-harga-juli-2026
- Panel Harga Pangan launch coverage: https://www.idxchannel.com/economics/antisipasi-gejolak-harga-dan-pasokan-nfa-luncurkan-panel-harga-pangan
- UU 28/2014 Pasal 43: https://pasal.id/peraturan/uu/uu-no-28-tahun-2014/pasal-43
- UU 28/2014 Pasal 44: https://pasal.id/peraturan/uu/uu-no-28-tahun-2014/pasal-44
