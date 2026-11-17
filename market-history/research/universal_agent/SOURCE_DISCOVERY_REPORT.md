# Session C source discovery checkpoint

The reviewed registry still allows US Treasury and NY Fed rate series. The June 2018 run collected UST 2Y, UST 10Y, and SOFR from those approved adapters. Treasury source SHA-256 was `a9278f347b48b819d68f91961e3e1a18431514ae3763ef888cc9f1bdb064b254`; NY Fed source SHA-256 was `b307e489026c74f22a13a13da1c9c606b3d6bd846f8d25fa40d00b3972725b62`. Values were checked, but historical first-access and revision evidence remains absent.

The May 2018 run discovered 23 weekdays and reserved three source requests. It collected data but blocked all collection tasks because the current weekday-only calendar treats `2018-05-28` as a required observation; the Treasury recovery checkpoint lists that date as `still_missing`. The `analyze_rates` dependency stayed blocked. This is a concrete calendar coverage defect, not evidence of source unavailability.

The existing official KRX access attempt record (`daily-index-validation-20261021/krx_access_attempts.json`) reports HTTP 400 `LOGOUT`, zero official price rows, and no API key. No KRX adapter was approved or added in this checkpoint. Korean index data remains exploratory and PIT unverified. Broader source registry and discovery are pending.
