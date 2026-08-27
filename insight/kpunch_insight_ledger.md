# 박종훈의 지식한방 인사이트 검증 원장

- 생성 시각(UTC): 2026-08-15T09:40:43+00:00
- 핵심 주장: 13개
- 원칙: 아래 문장은 내부 분석용 의역이며, 자막 원문은 재게시하지 않습니다.
- 상태: TRACKABLE=보유 지표 75% 이상, PARTIAL=일부 보유, NEEDS_DATA=추가 수집 필요

## 검증 준비 현황

- TRACKABLE: 5개 · PARTIAL: 6개 · NEEDS_DATA: 2개
- 우선 추가 수집: `foreign_equity_flow`(2개 주장), `bok_rp_purchase`(1개 주장), `kr_nominal_gdp_yoy`(1개 주장), `foreign_bond_flow`(1개 주장), `retail_sales_kr`(1개 주장), `real_household_income`(1개 주장), `household_debt_gdp`(1개 주장), `interest_expense`(1개 주장), `kr_fiscal_balance_gdp`(1개 주장), `working_age_population_kr`(1개 주장)

## KP-MON-001 · 통화정책 · TRACKABLE (80.0%)

**주장 의역:** 한국은행의 반복적인 RP 매입은 단기 안정을 주지만 채권시장의 가격 신호와 금융회사 규율을 약화시킬 수 있다.

**전달경로:** RP 매입 확대 → 채권 수요와 유동성 증가 → 위험 프리미엄 억제 → 도덕적 해이와 환율 부담

**대표 근거 위치**

- [한국은행의 끝없는 돈뿌리기, 이미 누적 RP 62조 돌파 (박종훈의 지식한방)](https://www.youtube.com/watch?v=0N_6lAviiIo&t=636s) · 10:36 · 검색 앵커: `가격 신호가 마비`
- [한국은행 62조 시장개입이 위험한 9가지 이유 (박종훈의 지식한방)](https://www.youtube.com/watch?v=T5pON5iwG64&t=493s) · 8:13 · 검색 앵커: `금융 시장을 길들여`

**검증 지표**

- ⬜ `bok_rp_purchase`: 추가 수집 필요
- ✅ `kr3y`: 3.7960 % (2026-08-01)
- ✅ `kr10y`: 4.3130 % (2026-08-01)
- ✅ `usdkrw`: 1,412.0000 KRW/USD (2026-08-01)
- ✅ `credit_spread`: 0.6960 %p (2026-08-01)

## KP-MON-002 · 통화가치 · TRACKABLE (80.0%)

**주장 의역:** 통화량이 실질성장보다 빠르게 증가하면 명목 자산가격은 오를 수 있지만 통화가치와 구매력은 약해질 수 있다.

**전달경로:** M2 증가 → 자산 수요 증가 → 명목가격 상승 → 물가·환율 상승 → 실질 구매력 저하

**대표 근거 위치**

- [환율 1475원 돌파, 주가는 더 위험하다 (박종훈의 지식한방)](https://www.youtube.com/watch?v=aWUXrtOp2Hg&t=189s) · 3:09 · 검색 앵커: `M2 통화량`
- [금값이 폭등한 게 아니라 돈 가치가 급락한 것이다 (박종훈의 지식한방)](https://www.youtube.com/watch?v=UNNfxQb9Sio&t=404s) · 6:44 · 검색 앵커: `돈 가치가 떨어`

**검증 지표**

- ✅ `kr_m2_yoy`: 5.9768 % YoY (2026-06-01)
- ✅ `us_m2_yoy`: 5.5258 % YoY (2026-06-01)
- ⬜ `kr_nominal_gdp_yoy`: 추가 수집 필요
- ✅ `usdkrw`: 1,412.0000 KRW/USD (2026-08-01)
- ✅ `kr_cpi_yoy`: 2.7892 % YoY (2026-07-01)

## KP-EQT-001 · 주식·실질수익 · TRACKABLE (100.0%)

**주장 의역:** 주가 상승은 환율과 물가를 반영한 실질·달러 기준으로 다시 평가해야 한다.

**전달경로:** 원화 주가지수 상승 → 원화 약세 또는 물가 상승 → 달러·실질 수익률 축소

**대표 근거 위치**

- [금값이 폭등한 게 아니라 돈 가치가 급락한 것이다 (박종훈의 지식한방)](https://www.youtube.com/watch?v=UNNfxQb9Sio&t=2s) · 0:02 · 검색 앵커: `돈 가치가 폭락`
- [주가는 오르는데, 원화는 왜 추락하나? (박종훈의 지식한방)](https://www.youtube.com/watch?v=FtPu3XGQ9p8&t=42s) · 0:42 · 검색 앵커: `원화`

**검증 지표**

- ✅ `kospi`: 6,977.9399 index (2026-08-01)
- ✅ `usdkrw`: 1,412.0000 KRW/USD (2026-08-01)
- ✅ `kr_cpi`: 119.7700 index (2026-07-01)
- ✅ `kospi_usd_real`: 398.3547 2003-12=100 (2026-07-01)

## KP-FX-001 · 환율 · PARTIAL (66.7%)

**주장 의역:** 원/달러 환율은 한국 금융정책의 신뢰와 해외자금 흐름을 먼저 보여주는 위험 경보다.

**전달경로:** 정책 신뢰 또는 금리차 변화 → 외국인 자금 이동 → 원/달러 반응 → 주식·채권·물가 전이

**대표 근거 위치**

- [한국은행의 끝없는 돈뿌리기, 이미 누적 RP 62조 돌파 (박종훈의 지식한방)](https://www.youtube.com/watch?v=0N_6lAviiIo&t=671s) · 11:11 · 검색 앵커: `탄광 속의 카나리아`
- [미국의 환율 조작국 위협에 원화 가치가 하락한 이유는? (박종훈의 지식한방)](https://www.youtube.com/watch?v=JrVYsBo8nDw&t=11s) · 0:11 · 검색 앵커: `환율 관찰 대상국`

**검증 지표**

- ✅ `usdkrw`: 1,412.0000 KRW/USD (2026-08-01)
- ✅ `kr_us_10y_gap`: -0.3170 %p (2026-08-01)
- ⬜ `foreign_equity_flow`: 추가 수집 필요
- ⬜ `foreign_bond_flow`: 추가 수집 필요
- ✅ `fx_reserves`: 427,948,361.0000 USD thousand (2026-07-01)
- ✅ `reer_kr`: 83.0600 index (2026-06-01)

## KP-HOU-001 · 부동산·금리 · PARTIAL (50.0%)

**주장 의역:** 한국은 내수가 약해도 집값과 가계부채, 환율 때문에 미국보다 빠른 금리 인하가 어렵다.

**전달경로:** 내수 둔화 → 금리 인하 압력 → 주택·가계대출 재상승 위험 → 환율 제약 → 정책 딜레마

**대표 근거 위치**

- [내수는 금융위기 이후 최악인데 부동산만 급등하는 이유는? (박종훈의 지식한방)](https://www.youtube.com/watch?v=WiXsuEGBvYI&t=86s) · 1:26 · 검색 앵커: `금리를 낮추고 싶어도`
- [3분기 GDP쇼크, 환율과 금리까지 흔들린다 (박종훈의 지식한방)](https://www.youtube.com/watch?v=GJXD5vQtxA4&t=1194s) · 19:54 · 검색 앵커: `우리만 빠르게 인하`

**검증 지표**

- ⬜ `retail_sales_kr`: 추가 수집 필요
- ⬜ `real_household_income`: 추가 수집 필요
- ✅ `seoul_house_price`: 104.6660 index (2026-07-01)
- ⬜ `household_debt_gdp`: 추가 수집 필요
- ✅ `usdkrw`: 1,412.0000 KRW/USD (2026-08-01)
- ✅ `bok_base_rate`: 2.7500 % (2026-07-01)

## KP-RATE-001 · 시장금리 · TRACKABLE (85.7%)

**주장 의역:** 기준금리 인하에도 장기금리가 오르면 실제 금융여건은 완화되지 않으며 국채 공급이 통화정책을 상쇄할 수 있다.

**전달경로:** 기준금리 인하 → 재정적자와 국채 공급 증가 → 기간 프리미엄 상승 → 장기금리 상승 → 금융여건 긴축

**대표 근거 위치**

- [금값이 폭등한 게 아니라 돈 가치가 급락한 것이다 (박종훈의 지식한방)](https://www.youtube.com/watch?v=UNNfxQb9Sio&t=602s) · 10:02 · 검색 앵커: `10년물 국채 금리는 오히려`
- [10년물 국채금리 4.5% 재돌파, 비상걸린 트럼프 (박종훈의 지식한방)](https://www.youtube.com/watch?v=l07sHuq0Uzk&t=18s) · 0:18 · 검색 앵커: `10년물`

**검증 지표**

- ✅ `bok_base_rate`: 2.7500 % (2026-07-01)
- ✅ `kr10y`: 4.3130 % (2026-08-01)
- ✅ `kr30y`: 4.6690 % (2026-08-01)
- ✅ `us10y`: 4.6300 % (2026-08-01)
- ✅ `us30y`: 5.2100 % (2026-08-01)
- ✅ `sovereign_issuance`: 20,183.0000 KRW billion/month (2026-06-01)
- ⬜ `interest_expense`: 추가 수집 필요

## KP-FIS-001 · 재정 · TRACKABLE (80.0%)

**주장 의역:** 비기축통화국인 한국이 경기부양을 국채에 계속 의존하면 금리와 환율 부담 때문에 지속성 한계에 직면한다.

**전달경로:** 적자재정 → 국채 발행 → 부채 증가 → 국채금리·환율 상승 → 추가 부양 여력 축소

**대표 근거 위치**

- [3분기 GDP쇼크, 환율과 금리까지 흔들린다 (박종훈의 지식한방)](https://www.youtube.com/watch?v=GJXD5vQtxA4&t=804s) · 13:24 · 검색 앵커: `정부주도 성장`
- [환율 1475원 돌파, 주가는 더 위험하다 (박종훈의 지식한방)](https://www.youtube.com/watch?v=aWUXrtOp2Hg&t=962s) · 16:02 · 검색 앵커: `적자 국채`

**검증 지표**

- ⬜ `kr_fiscal_balance_gdp`: 추가 수집 필요
- ✅ `kr_debt_gdp`: 49.7000 % GDP (2024)
- ✅ `sovereign_issuance`: 20,183.0000 KRW billion/month (2026-06-01)
- ✅ `kr10y`: 4.3130 % (2026-08-01)
- ✅ `usdkrw`: 1,412.0000 KRW/USD (2026-08-01)

## KP-DEM-001 · 인구·부채 · PARTIAL (20.0%)

**주장 의역:** 한국 재정의 핵심 위험은 현재 부채 수준보다 저성장·고령화·생산연령인구 감소가 결합된 증가 속도다.

**전달경로:** 생산연령인구 감소 → 성장·세입 둔화 → 복지지출 증가 → 재정적자 확대 → 부채비율 상승

**대표 근거 위치**

- [미국 국가부채 사상 첫 37조 달러 돌파, 과연 한국은 안전한가? (박종훈의 지식한방)](https://www.youtube.com/watch?v=Sop9n4HXnf0&t=852s) · 14:12 · 검색 앵커: `생산 연령 인구`
- [최대 인구 집단 베이비부머의 은퇴, 경제 충격이 '이 정도'라고? (박종훈의 지식한방)](https://www.youtube.com/watch?v=A1eCmFSFpIE&t=836s) · 13:56 · 검색 앵커: `베이비부머`

**검증 지표**

- ✅ `kr_debt_gdp`: 49.7000 % GDP (2024)
- ⬜ `working_age_population_kr`: 추가 수집 필요
- ⬜ `old_age_dependency_kr`: 추가 수집 필요
- ⬜ `potential_growth_kr`: 추가 수집 필요
- ⬜ `welfare_spending_gdp`: 추가 수집 필요

## KP-TRADE-001 · 교역조건 · PARTIAL (16.7%)

**주장 의역:** 원화 약세는 수출을 자동으로 개선하지 않으며 중간재·에너지 수입물가를 통해 기업과 가계에 부담을 줄 수 있다.

**전달경로:** 원화 약세 → 수입물가 상승 → 기업 원가·소비자물가 상승 → 내수와 마진 압박

**대표 근거 위치**

- [3분기 GDP쇼크, 환율과 금리까지 흔들린다 (박종훈의 지식한방)](https://www.youtube.com/watch?v=GJXD5vQtxA4&t=1223s) · 20:23 · 검색 앵커: `수입 물가`
- [트럼프 당선 이후, 환율 폭등하고 코스피만 헤매는 진짜 이유 (박종훈의 지식한방)](https://www.youtube.com/watch?v=9vOGhjSKQhI&t=33s) · 0:33 · 검색 앵커: `환율`

**검증 지표**

- ✅ `usdkrw`: 1,412.0000 KRW/USD (2026-08-01)
- ⬜ `export_volume_kr`: 추가 수집 필요
- ⬜ `import_price_kr`: 추가 수집 필요
- ⬜ `terms_of_trade_kr`: 추가 수집 필요
- ⬜ `energy_import_bill`: 추가 수집 필요
- ⬜ `operating_margin_kr`: 추가 수집 필요

## KP-EQT-002 · 한국증시 · PARTIAL (28.6%)

**주장 의역:** 한국 증시의 급등은 실물경제 개선과 분리될 수 있으며 외국인 자금·환율·반도체 사이클·정책 수급을 함께 봐야 한다.

**전달경로:** 외국인·정책 수급 변화 → 대형 반도체 가격 변화 → 지수 급등락 → 실물지표와 괴리

**대표 근거 위치**

- [걸핏하면 급등락, 코스피 왜 이러나? (박종훈의 지식한방)](https://www.youtube.com/watch?v=37ooENAKSPc&t=0s) · 0:00 · 검색 앵커: `코스피`
- [삼성 실적에도 주가 급락, 코스피 반등 위한 3가지 조건 (박종훈의 지식한방)](https://www.youtube.com/watch?v=J6xA-6pjP8I&t=80s) · 1:20 · 검색 앵커: `삼성`

**검증 지표**

- ✅ `kospi`: 6,977.9399 index (2026-08-01)
- ⬜ `foreign_equity_flow`: 추가 수집 필요
- ✅ `usdkrw`: 1,412.0000 KRW/USD (2026-08-01)
- ⬜ `semiconductor_exports`: 추가 수집 필요
- ⬜ `memory_price`: 추가 수집 필요
- ⬜ `samsung_sk_profit`: 추가 수집 필요
- ⬜ `pension_flow`: 추가 수집 필요

## KP-HOU-002 · 부동산·금융안정 · PARTIAL (16.7%)

**주장 의역:** 부동산 부양은 단기 가격을 지지하지만 가계부채·PF 위험·지역 격차와 자본의 비생산적 배분을 심화할 수 있다.

**전달경로:** 규제 완화와 유동성 → 서울 가격 상승 → 대출·PF 확대 → 지역 양극화 → 금융안정 부담

**대표 근거 위치**

- [정부가 억지로 끌어올린 서울 집값...나중에 폭탄된다 (박종훈의 지식한방)](https://www.youtube.com/watch?v=CIB88CNbvKU&t=63s) · 1:03 · 검색 앵커: `부동산 부양책`
- [역대 최악의 부채 폭증, 집값까지 요동친다 (박종훈의 지식한방)](https://www.youtube.com/watch?v=Jdu3Nq-T4nA&t=8s) · 0:08 · 검색 앵커: `GDP 대비 부채`

**검증 지표**

- ✅ `seoul_house_price`: 104.6660 index (2026-07-01)
- ⬜ `regional_house_price`: 추가 수집 필요
- ⬜ `housing_transactions`: 추가 수집 필요
- ⬜ `household_credit`: 추가 수집 필요
- ⬜ `pf_delinquency`: 추가 수집 필요
- ⬜ `unsold_housing`: 추가 수집 필요

## KP-CHN-001 · 중국경제 · NEEDS_DATA (0.0%)

**주장 의역:** 중국의 둔화는 부동산 의존·디플레이션·외국인투자 감소·정책 신뢰 하락이 겹친 구조적 문제다.

**전달경로:** 부동산 조정 → 내수·물가 약화 → FDI 감소 → 성장률 둔화 → 한국 수출 전이

**대표 근거 위치**

- [시진핑 집권 12년, 수렁에 빠진 중국 경제 (박종훈의 지식한방)](https://www.youtube.com/watch?v=6JP6WNhpJhQ&t=973s) · 16:13 · 검색 앵커: `해외 직접 투자`
- [중국산은 이제 안사요... 최악의 디플레 불렀다 (박종훈의 지식한방)](https://www.youtube.com/watch?v=8_Gj4VjmIVs&t=0s) · 0:00 · 검색 앵커: `디플레`

**검증 지표**

- ⬜ `china_house_price`: 추가 수집 필요
- ⬜ `china_cpi_yoy`: 추가 수집 필요
- ⬜ `china_ppi_yoy`: 추가 수집 필요
- ⬜ `china_fdi`: 추가 수집 필요
- ⬜ `china_real_gdp_yoy`: 추가 수집 필요
- ⬜ `kr_exports_china`: 추가 수집 필요

## KP-AI-001 · AI·산업 · NEEDS_DATA (0.0%)

**주장 의역:** AI 시대의 지속 가능한 승자는 모델뿐 아니라 전력·데이터센터·반도체·플랫폼과 자본조달 능력을 확보한 기업이다.

**전달경로:** AI 수요 증가 → 컴퓨팅·전력 병목 → 대규모 설비투자 → 인프라·반도체 이익 집중

**대표 근거 위치**

- [AI후진국으로 전락한 한국, 반도체 산업이 살아날 길은? (한국경제부활 프로젝트3, 박종훈의 지식한방)](https://www.youtube.com/watch?v=A0s34BV_8Gc&t=319s) · 5:19 · 검색 앵커: `거대 언어 모델`
- [한국 인터넷 속도 하위권, 어쩌다 IT강국이 AI후진국이 됐나? (박종훈의 지식한방)](https://www.youtube.com/watch?v=mVOkY5VAVCw&t=15s) · 0:15 · 검색 앵커: `데이터센터`

**검증 지표**

- ⬜ `hyperscaler_capex`: 추가 수집 필요
- ⬜ `data_center_power`: 추가 수집 필요
- ⬜ `gpu_shipments`: 추가 수집 필요
- ⬜ `hbm_revenue`: 추가 수집 필요
- ⬜ `electricity_reserve_margin_kr`: 추가 수집 필요
- ⬜ `free_cash_flow`: 추가 수집 필요

