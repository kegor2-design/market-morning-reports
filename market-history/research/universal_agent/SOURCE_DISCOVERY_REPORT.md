# Session C source discovery checkpoint

## 2020 Treasury archive and schema — 2026-11-18

The [Treasury's official archive index](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rate-archives) lists par yield curve files for 2010-2019 and 2020-2023. The existing adapter had incorrectly constructed a 2020-2029 URL; it now uses the listed 2020-2023 file and fails closed for later years until reviewed. The actual 2020 response uses lowercase column labels and four-digit dates, while the older archive used title case and two-digit dates. The parser now accepts either reviewed shape, still requires the selected tenor and date field, and rejects unknown layouts. 2020 Treasury and NY Fed responses were actually collected. Historical first-publication and first-access timestamps remain unverified; no official investment claim is authorized.

## 2026-11-18 AI proposal source gate

The new candidate validator accepts only the approved sources already present in the host Research Program and rejects an unreviewed provider before queue registration. This is a registry-policy test, not discovery of a new source. No additional official Korean data, source access approval, or historical PIT timestamp was obtained in this continuation.

## 2026-11-18 calendar and source verification

The [SIFMA historical holiday archive](https://www.sifma.org/resources/guides-playbooks/us-holiday-archive) lists full closures on 2018-05-28, 2018-07-04, and 2019-05-27. [NY Fed reference-rate methodology](https://www.newyorkfed.org/markets/reference-rates/additional-information-about-reference-rates) says SOFR is not calculated for SIFMA full-closure days; SOFR's value date is distinct from its publication date. [Treasury's interest-rate statistics](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics?data=yieldyear&year=2018) show 2018-05-25 and 2018-05-29 around the May closure. The calendar module records full closures for 2018 and 2019, source-specific publication metadata, and no historical first-access claim. Other years fail closed in this recovery path.

May 2018 and May 2019 source payloads were parsed again from their sealed original responses; no replacement value was imputed and no extra network request was made. May 2018 Treasury SHA-256 remains `a9278f347b48b819d68f91961e3e1a18431514ae3763ef888cc9f1bdb064b254`; its NY Fed SHA-256 remains `8ae59c6fec33ebbc20778db9d6931b58d3c336d21fd990f6e7307e75e5120830`. May 2019 NY Fed SHA-256 is `3a8ba10a41fde4cf010f96e2e8a444fa38d144fe22182da4a732ab409145d018`. Values were independently re-parsed and remain PIT unverified.

The reviewed registry still allows US Treasury and NY Fed rate series. The June 2018 run collected UST 2Y, UST 10Y, and SOFR from those approved adapters. Treasury source SHA-256 was `a9278f347b48b819d68f91961e3e1a18431514ae3763ef888cc9f1bdb064b254`; NY Fed source SHA-256 was `b307e489026c74f22a13a13da1c9c606b3d6bd846f8d25fa40d00b3972725b62`. Values were checked, but historical first-access and revision evidence remains absent.

The original May 2018 run discovered 23 weekdays and reserved three source requests. It initially blocked all collection tasks because the weekday-only calendar treated `2018-05-28` as a required observation. The versioned calendar recovery resolved this coverage defect; the original blocked records remain as historical evidence.

The existing official KRX access attempt record (`daily-index-validation-20261021/krx_access_attempts.json`) reports HTTP 400 `LOGOUT`, zero official price rows, and no API key. No KRX adapter was approved or added in this checkpoint. Korean index data remains exploratory and PIT unverified. Broader source registry and discovery are pending.
