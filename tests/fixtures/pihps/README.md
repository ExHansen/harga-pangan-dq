# Recorded PIHPS responses

These are byte-exact response bodies recorded by `hpdq ingest --date 2026-11-11` on 2026-11-12
(UTC 10:49–10:50) with the project User-Agent. The test suite serves them through
`httpx.MockTransport`, so **tests never hit the network**.

| File | Request | SHA-256 (first 12) |
|---|---|---|
| `ref_commodities.json` | `GetRefCommodityAndCategory` | `af6439603c17` |
| `ref_provinces.json` | `GetRefProvince` | `5aea0bf16fb7` |
| `grid_com_13_20261104-20261111_k1.json` | `GetGridDataKomoditas`, Cabai Merah Besar, 2026-11-04..11, cities | `67d124ec69d9` |
| `grid_com_14_20261104-20261111_k1.json` | same, Cabai Merah Keriting | `c4d911018888` |
| `grid_com_15_20261104-20261111_k1.json` | same, Cabai Rawit Hijau | `ccd443ff9a08` |
| `grid_com_16_20261104-20261111_k1.json` | same, Cabai Rawit Merah | `76136d5b296a` |

`.gitattributes` marks this folder `-text`, so line-ending conversion never changes the bytes or
the hashes.

Source: Pusat Informasi Harga Pangan Strategis (PIHPS) Nasional, Bank Indonesia,
<https://www.bi.go.id/hargapangan>. This small sample is included for testing and research, with
the source cited (UU 28/2014 Pasal 44(1)(a)). It is not an official statistic.
