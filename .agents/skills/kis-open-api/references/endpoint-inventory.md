# KIS endpoint inventory (generated)

Generated from `examples_llm/` of `koreainvestment/open-trading-api` (clone date 2026-08-26). One row per upstream sample folder. Rows with an empty tr_id build it dynamically from parameters; open the sample. `(websocket)` rows are realtime subscriptions (see websocket.md).

Regenerate: `scripts/find_kis_endpoint.sh --inventory > references/endpoint-inventory.md`

| category | upstream folder | path | tr_id(s) | title |
|---|---|---|---|---|
| auth | auth_token | /oauth2/tokenP |  |  |
| auth | auth_ws_token | /oauth2/Approval |  |  |
| domestic_bond | avg_unit | /uapi/domestic-bond/v1/quotations/avg-unit | CTPF2005R | 장내채권 평균단가조회 |
| domestic_bond | bond_asking_price | (websocket) | H0BJASP0 | 일반채권 실시간호가 |
| domestic_bond | bond_ccnl | (websocket) | H0BJCNT0 | 일반채권 실시간체결가 |
| domestic_bond | bond_index_ccnl | (websocket) | H0BICNT0 | 채권지수 실시간체결가 |
| domestic_bond | buy | /uapi/domestic-bond/v1/trading/buy | TTTC0952U | 장내채권 매수주문 |
| domestic_bond | inquire_asking_price | /uapi/domestic-bond/v1/quotations/inquire-asking-price | FHKBJ773401C0 | 장내채권현재가(호가) |
| domestic_bond | inquire_balance | /uapi/domestic-bond/v1/trading/inquire-balance | CTSC8407R | 장내채권 잔고조회 |
| domestic_bond | inquire_ccnl | /uapi/domestic-bond/v1/quotations/inquire-ccnl | FHKBJ773403C0 | 장내채권현재가(체결) |
| domestic_bond | inquire_daily_ccld | /uapi/domestic-bond/v1/trading/inquire-daily-ccld | CTSC8013R | 장내채권 일별체결조회 |
| domestic_bond | inquire_daily_itemchartprice | /uapi/domestic-bond/v1/quotations/inquire-daily-itemchartprice | FHKBJ773701C0 | 장내채권 기간별시세(일) |
| domestic_bond | inquire_daily_price | /uapi/domestic-bond/v1/quotations/inquire-daily-price | FHKBJ773404C0 | 장내채권현재가(일별) |
| domestic_bond | inquire_price | /uapi/domestic-bond/v1/quotations/inquire-price | FHKBJ773400C0 | 장내채권현재가(시세) |
| domestic_bond | inquire_psbl_order | /uapi/domestic-bond/v1/trading/inquire-psbl-order | TTTC8910R | 장내채권 매수가능조회 |
| domestic_bond | inquire_psbl_rvsecncl | /uapi/domestic-bond/v1/trading/inquire-psbl-rvsecncl | CTSC8035R | 채권정정취소가능주문조회 |
| domestic_bond | issue_info | /uapi/domestic-bond/v1/quotations/issue-info | CTPF1101R | 장내채권 발행정보 |
| domestic_bond | order_rvsecncl | /uapi/domestic-bond/v1/trading/order-rvsecncl | TTTC0953U | 장내채권 정정취소주문 |
| domestic_bond | search_bond_info | /uapi/domestic-bond/v1/quotations/search-bond-info | CTPF1114R | 장내채권 기본조회 |
| domestic_bond | sell | /uapi/domestic-bond/v1/trading/sell | TTTC0958U | 장내채권 매도주문 |
| domestic_futureoption | commodity_futures_realtime_conclusion | (websocket) | H0CFCNT0 | 상품선물 실시간체결가 |
| domestic_futureoption | commodity_futures_realtime_quote | (websocket) | H0CFASP0 | 상품선물 실시간호가 |
| domestic_futureoption | display_board_callput | /uapi/domestic-futureoption/v1/quotations/display-board-callput | FHPIF05030100 | 국내옵션전광판_콜풋 |
| domestic_futureoption | display_board_futures | /uapi/domestic-futureoption/v1/quotations/display-board-futures | FHPIF05030200 | 국내옵션전광판_선물 |
| domestic_futureoption | display_board_option_list | /uapi/domestic-futureoption/v1/quotations/display-board-option-list | FHPIO056104C0 | 국내옵션전광판_옵션월물리스트 |
| domestic_futureoption | display_board_top | /uapi/domestic-futureoption/v1/quotations/display-board-top | FHPIF05030000 | 국내선물 기초자산 시세 |
| domestic_futureoption | exp_price_trend | /uapi/domestic-futureoption/v1/quotations/exp-price-trend | FHPIF05110100 | 선물옵션 일중예상체결추이 |
| domestic_futureoption | fuopt_ccnl_notice | (websocket) | H0IFCNI0 | 선물옵션 실시간체결통보 |
| domestic_futureoption | futures_exp_ccnl | (websocket) | H0ZFANC0 | 주식선물 실시간예상체결 |
| domestic_futureoption | index_futures_realtime_conclusion | (websocket) | H0IFCNT0 | 지수선물 실시간체결가 |
| domestic_futureoption | index_futures_realtime_quote | (websocket) | H0IFASP0 | 지수선물 실시간호가 |
| domestic_futureoption | index_option_realtime_conclusion | (websocket) | H0IOCNT0 | 지수옵션 실시간체결가 |
| domestic_futureoption | index_option_realtime_quote | (websocket) | H0IOASP0 | 지수옵션 실시간호가 |
| domestic_futureoption | inquire_asking_price | /uapi/domestic-futureoption/v1/quotations/inquire-asking-price | FHMIF10010000 | 선물옵션 시세호가 |
| domestic_futureoption | inquire_balance | /uapi/domestic-futureoption/v1/trading/inquire-balance | CTFO6118R, VTFO6118R | 선물옵션 잔고현황 |
| domestic_futureoption | inquire_balance_settlement_pl | /uapi/domestic-futureoption/v1/trading/inquire-balance-settlement-pl | CTFO6117R | 선물옵션 잔고정산손익내역 |
| domestic_futureoption | inquire_balance_valuation_pl | /uapi/domestic-futureoption/v1/trading/inquire-balance-valuation-pl | CTFO6159R | 선물옵션 잔고평가손익내역 |
| domestic_futureoption | inquire_ccnl | /uapi/domestic-futureoption/v1/trading/inquire-ccnl | TTTO5201R, VTTO5201R | 선물옵션 주문체결내역조회 |
| domestic_futureoption | inquire_ccnl_bstime | /uapi/domestic-futureoption/v1/trading/inquire-ccnl-bstime | CTFO5139R | 선물옵션 기준일체결내역 |
| domestic_futureoption | inquire_daily_amount_fee | /uapi/domestic-futureoption/v1/trading/inquire-daily-amount-fee | CTFO6119R | 선물옵션기간약정수수료일별 |
| domestic_futureoption | inquire_daily_fuopchartprice | /uapi/domestic-futureoption/v1/quotations/inquire-daily-fuopchartprice | FHKIF03020100 | 선물옵션기간별시세(일/주/월/년) |
| domestic_futureoption | inquire_deposit | /uapi/domestic-futureoption/v1/trading/inquire-deposit | CTRP6550R | 선물옵션 총자산현황 |
| domestic_futureoption | inquire_ngt_balance | /uapi/domestic-futureoption/v1/trading/inquire-ngt-balance | CTFN6118R | (야간)선물옵션 잔고현황 |
| domestic_futureoption | inquire_ngt_ccnl | /uapi/domestic-futureoption/v1/trading/inquire-ngt-ccnl |  | (야간)선물옵션 주문체결 내역조회 |
| domestic_futureoption | inquire_price | /uapi/domestic-futureoption/v1/quotations/inquire-price | FHMIF10000000 | 선물옵션 시세 |
| domestic_futureoption | inquire_psbl_ngt_order | /uapi/domestic-futureoption/v1/trading/inquire-psbl-ngt-order |  | (야간)선물옵션 주문가능 조회 |
| domestic_futureoption | inquire_psbl_order | /uapi/domestic-futureoption/v1/trading/inquire-psbl-order | TTTO5105R, VTTO5105R | 선물옵션 주문가능 |
| domestic_futureoption | inquire_time_fuopchartprice | /uapi/domestic-futureoption/v1/quotations/inquire-time-fuopchartprice | FHKIF03020200 | 선물옵션 분봉조회 |
| domestic_futureoption | krx_ngt_futures_asking_price | (websocket) | H0MFASP0 | KRX야간선물 실시간호가 |
| domestic_futureoption | krx_ngt_futures_ccnl | (websocket) | H0MFCNT0 | KRX야간선물 실시간종목체결 |
| domestic_futureoption | krx_ngt_futures_ccnl_notice | (websocket) | H0MFCNI0 | KRX야간선물 실시간체결통보 |
| domestic_futureoption | krx_ngt_option_asking_price | (websocket) | H0EUASP0 | KRX야간옵션 실시간호가 |
| domestic_futureoption | krx_ngt_option_ccnl | (websocket) | H0EUCNT0 | KRX야간옵션 실시간체결가 |
| domestic_futureoption | krx_ngt_option_exp_ccnl | (websocket) | H0EUANC0 | KRX야간옵션실시간예상체결 |
| domestic_futureoption | krx_ngt_option_notice | (websocket) | H0EUCNI0 | KRX야간옵션실시간체결통보 |
| domestic_futureoption | ngt_margin_detail | /uapi/domestic-futureoption/v1/trading/ngt-margin-detail | CTFN7107R | (야간)선물옵션 증거금 상세 |
| domestic_futureoption | option_exp_ccnl | (websocket) | H0ZOANC0 | 주식옵션 실시간예상체결 |
| domestic_futureoption | order | /uapi/domestic-futureoption/v1/trading/order | TTTO1101U, VTTO1101U | 선물옵션 주문 |
| domestic_futureoption | order_rvsecncl | /uapi/domestic-futureoption/v1/trading/order-rvsecncl | TTTN1103U, TTTO1103U, VTTO1103U | 선물옵션 정정취소주문 |
| domestic_futureoption | stock_futures_realtime_conclusion | (websocket) | H0ZFCNT0 | 주식선물 실시간체결가 |
| domestic_futureoption | stock_futures_realtime_quote | (websocket) | H0ZFASP0 | 주식선물 실시간호가 |
| domestic_futureoption | stock_option_asking_price | (websocket) | H0ZOASP0 | 주식옵션 실시간호가 |
| domestic_futureoption | stock_option_ccnl | (websocket) | H0ZOCNT0 | 주식옵션 실시간체결가 |
| domestic_stock | after_hour_balance | /uapi/domestic-stock/v1/ranking/after-hour-balance | FHPST01760000 | 국내주식 시간외잔량 순위 |
| domestic_stock | asking_price_krx | (websocket) | H0STASP0 | 국내주식 실시간호가 (KRX) |
| domestic_stock | asking_price_nxt | (websocket) | H0NXASP0 | 국내주식 실시간호가 (NXT) |
| domestic_stock | asking_price_total | (websocket) | H0UNASP0 | 국내주식 실시간호가 (통합) |
| domestic_stock | bulk_trans_num | /uapi/domestic-stock/v1/ranking/bulk-trans-num | FHKST190900C0 | 국내주식 대량체결건수 상위 |
| domestic_stock | capture_uplowprice | /uapi/domestic-stock/v1/quotations/capture-uplowprice | FHKST130000C0 | 국내주식 상하한가 포착 |
| domestic_stock | ccnl_krx | (websocket) | H0STCNT0 | 국내주식 실시간체결가(KRX) |
| domestic_stock | ccnl_notice | (websocket) | H0STCNI0, H0STCNI9 | 국내주식 주식체결통보 |
| domestic_stock | ccnl_nxt | (websocket) | H0NXCNT0 | 국내주식 실시간체결가 (NXT) |
| domestic_stock | ccnl_total | (websocket) | H0UNCNT0 | 국내주식 실시간체결가 (통합) |
| domestic_stock | chk_holiday | /uapi/domestic-stock/v1/quotations/chk-holiday | CTCA0903R | 국내휴장일조회 |
| domestic_stock | comp_interest | /uapi/domestic-stock/v1/quotations/comp-interest | FHPST07020000 | 금리 종합(국내채권_금리) |
| domestic_stock | comp_program_trade_daily | /uapi/domestic-stock/v1/quotations/comp-program-trade-daily | FHPPG04600001 | 프로그램매매 종합현황(일별) |
| domestic_stock | comp_program_trade_today | /uapi/domestic-stock/v1/quotations/comp-program-trade-today | FHPPG04600101 | 프로그램매매 종합현황(시간) |
| domestic_stock | credit_balance | /uapi/domestic-stock/v1/ranking/credit-balance | FHKST17010000 | 국내주식 신용잔고 상위 |
| domestic_stock | credit_by_company | /uapi/domestic-stock/v1/quotations/credit-by-company | FHPST04770000 | 국내주식 당사 신용가능종목 |
| domestic_stock | daily_credit_balance | /uapi/domestic-stock/v1/quotations/daily-credit-balance | FHPST04760000 | 국내주식 신용잔고 일별추이 |
| domestic_stock | daily_loan_trans | /uapi/domestic-stock/v1/quotations/daily-loan-trans | HHPST074500C0 | 종목별 일별 대차거래추이 |
| domestic_stock | daily_short_sale | /uapi/domestic-stock/v1/quotations/daily-short-sale | FHPST04830000 | 국내주식 공매도 일별추이 |
| domestic_stock | disparity | /uapi/domestic-stock/v1/ranking/disparity | FHPST01780000 | 국내주식 이격도 순위 |
| domestic_stock | dividend_rate | /uapi/domestic-stock/v1/ranking/dividend-rate | HHKDB13470100 | 국내주식 배당률 상위 |
| domestic_stock | estimate_perform | /uapi/domestic-stock/v1/quotations/estimate-perform | HHKST668300C0 | 국내주식 종목추정실적 |
| domestic_stock | exp_ccnl_krx | (websocket) | H0STANC0 | 국내주식 실시간예상체결 (KRX) |
| domestic_stock | exp_ccnl_nxt | (websocket) | H0NXANC0 | 국내주식 실시간예상체결 (NXT) |
| domestic_stock | exp_ccnl_total | (websocket) | H0UNANC0 | 국내주식 실시간예상체결(통합) |
| domestic_stock | exp_closing_price | /uapi/domestic-stock/v1/quotations/exp-closing-price | FHKST117300C0 | 국내주식 장마감 예상체결가 |
| domestic_stock | exp_index_trend | /uapi/domestic-stock/v1/quotations/exp-index-trend | FHPST01840000 | 국내주식 예상체결지수 추이 |
| domestic_stock | exp_price_trend | /uapi/domestic-stock/v1/quotations/exp-price-trend | FHPST01810000 | 국내주식 예상체결가 추이 |
| domestic_stock | exp_total_index | /uapi/domestic-stock/v1/quotations/exp-total-index | FHKUP11750000 | 국내주식 예상체결 전체지수 |
| domestic_stock | exp_trans_updown | /uapi/domestic-stock/v1/ranking/exp-trans-updown | FHPST01820000 | 국내주식 예상체결 상승_하락상위 |
| domestic_stock | finance_balance_sheet | /uapi/domestic-stock/v1/finance/balance-sheet | FHKST66430100 | 국내주식 대차대조표 |
| domestic_stock | finance_financial_ratio | /uapi/domestic-stock/v1/finance/financial-ratio | FHKST66430300 | 국내주식 재무비율 |
| domestic_stock | finance_growth_ratio | /uapi/domestic-stock/v1/finance/growth-ratio | FHKST66430800 | 국내주식 성장성비율 |
| domestic_stock | finance_income_statement | /uapi/domestic-stock/v1/finance/income-statement | FHKST66430200 | 국내주식 손익계산서 |
| domestic_stock | finance_other_major_ratios | /uapi/domestic-stock/v1/finance/other-major-ratios | FHKST66430500 | 국내주식 기타주요비율 |
| domestic_stock | finance_profit_ratio | /uapi/domestic-stock/v1/finance/profit-ratio | FHKST66430400 | 국내주식 수익성비율 |
| domestic_stock | finance_ratio | /uapi/domestic-stock/v1/ranking/finance-ratio | FHPST01750000 | 국내주식 재무비율 순위 |
| domestic_stock | finance_stability_ratio | /uapi/domestic-stock/v1/finance/stability-ratio | FHKST66430600 | 국내주식 안정성비율 |
| domestic_stock | fluctuation | /uapi/domestic-stock/v1/ranking/fluctuation | FHPST01700000 | 등락률 순위 |
| domestic_stock | foreign_institution_total | /uapi/domestic-stock/v1/quotations/foreign-institution-total | FHPTJ04400000 | 국내기관_외국인 매매종목가집계 |
| domestic_stock | frgnmem_pchs_trend | /uapi/domestic-stock/v1/quotations/frgnmem-pchs-trend | FHKST644400C0 | 종목별 외국계 순매수추이 |
| domestic_stock | frgnmem_trade_estimate | /uapi/domestic-stock/v1/quotations/frgnmem-trade-estimate | FHKST644100C0 | 외국계 매매종목 가집계 |
| domestic_stock | frgnmem_trade_trend | /uapi/domestic-stock/v1/quotations/frgnmem-trade-trend | FHPST04320000 | 회원사 실 시간 매매동향(틱) |
| domestic_stock | hts_top_view | /uapi/domestic-stock/v1/ranking/hts-top-view | HHMCM000100C0 | HTS조회상위20종목 |
| domestic_stock | index_ccnl | (websocket) | H0UPCNT0 | 국내지수 실시간체결 |
| domestic_stock | index_exp_ccnl | (websocket) | H0UPANC0 | 국내지수 실시간예상체결 |
| domestic_stock | index_program_trade | (websocket) | H0UPPGM0 | 국내지수 실시간프로그램매매 |
| domestic_stock | inquire_account_balance | /uapi/domestic-stock/v1/trading/inquire-account-balance | CTRP6548R | 투자계좌자산현황조회 |
| domestic_stock | inquire_asking_price_exp_ccn | /uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn | FHKST01010200 | 주식현재가 호가/예상체결 |
| domestic_stock | inquire_balance | /uapi/domestic-stock/v1/trading/inquire-balance | TTTC8434R, VTTC8434R | 주식잔고조회 |
| domestic_stock | inquire_balance_rlz_pl | /uapi/domestic-stock/v1/trading/inquire-balance-rlz-pl | TTTC8494R | 주식잔고조회_실현손익 |
| domestic_stock | inquire_ccnl | /uapi/domestic-stock/v1/quotations/inquire-ccnl | FHKST01010300 | 주식현재가 체결 |
| domestic_stock | inquire_credit_psamount | /uapi/domestic-stock/v1/trading/inquire-credit-psamount | TTTC8909R | 신용매수가능조회 |
| domestic_stock | inquire_daily_ccld | /uapi/domestic-stock/v1/trading/inquire-daily-ccld | CTSC9215R, TTTC0081R, VTSC9215R, VTTC0081R | 주식일별주문체결조회 |
| domestic_stock | inquire_daily_indexchartprice | /uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice | FHKUP03500100 | 국내주식업종기간별시세(일_주_월_년) |
| domestic_stock | inquire_daily_itemchartprice | /uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice | FHKST03010100 | 국내주식기간별시세(일/주/월/년) |
| domestic_stock | inquire_daily_overtimeprice | /uapi/domestic-stock/v1/quotations/inquire-daily-overtimeprice | FHPST02320000 | 주식현재가 시간외일자별주가 |
| domestic_stock | inquire_daily_price | /uapi/domestic-stock/v1/quotations/inquire-daily-price | FHKST01010400 | 주식현재가 일자별 |
| domestic_stock | inquire_daily_trade_volume | /uapi/domestic-stock/v1/quotations/inquire-daily-trade-volume | FHKST03010800 | 종목별일별매수매도체결량 |
| domestic_stock | inquire_elw_price | /uapi/domestic-stock/v1/quotations/inquire-elw-price | FHKEW15010000 | ELW 현재가 시세 |
| domestic_stock | inquire_index_category_price | /uapi/domestic-stock/v1/quotations/inquire-index-category-price | FHPUP02140000 | 국내업종 구분별전체시세 |
| domestic_stock | inquire_index_daily_price | /uapi/domestic-stock/v1/quotations/inquire-index-daily-price | FHPUP02120000 | 국내업종 일자별지수 |
| domestic_stock | inquire_index_price | /uapi/domestic-stock/v1/quotations/inquire-index-price | FHPUP02100000 | 국내업종 현재지수 |
| domestic_stock | inquire_index_tickprice | /uapi/domestic-stock/v1/quotations/inquire-index-tickprice | FHPUP02110100 | 국내업종 시간별지수(초) |
| domestic_stock | inquire_index_timeprice | /uapi/domestic-stock/v1/quotations/inquire-index-timeprice | FHPUP02110200 | 국내업종 시간별지수(분) |
| domestic_stock | inquire_investor | /uapi/domestic-stock/v1/quotations/inquire-investor | FHKST01010900 | 주식현재가 투자자 |
| domestic_stock | inquire_investor_daily_by_market | /uapi/domestic-stock/v1/quotations/inquire-investor-daily-by-market | FHPTJ04040000 | 시장별 투자자매매동향(일별) |
| domestic_stock | inquire_investor_time_by_market | /uapi/domestic-stock/v1/quotations/inquire-investor-time-by-market | FHPTJ04030000 | 시장별 투자자매매동향(시세) |
| domestic_stock | inquire_member | /uapi/domestic-stock/v1/quotations/inquire-member | FHKST01010600 | 주식현재가 회원사 |
| domestic_stock | inquire_member_daily | /uapi/domestic-stock/v1/quotations/inquire-member-daily | FHPST04540000 | 주식현재가 회원사 종목매매동향 |
| domestic_stock | inquire_overtime_asking_price | /uapi/domestic-stock/v1/quotations/inquire-overtime-asking-price | FHPST02300400 | 국내주식 시간외호가 |
| domestic_stock | inquire_overtime_price | /uapi/domestic-stock/v1/quotations/inquire-overtime-price | FHPST02300000 | 국내주식 시간외현재가 |
| domestic_stock | inquire_period_profit | /uapi/domestic-stock/v1/trading/inquire-period-profit | TTTC8708R | 기간별손익일별합산조회 |
| domestic_stock | inquire_period_trade_profit | /uapi/domestic-stock/v1/trading/inquire-period-trade-profit | TTTC8715R | 기간별매매손익현황조회 |
| domestic_stock | inquire_price | /uapi/domestic-stock/v1/quotations/inquire-price | FHKST01010100 | 주식현재가 시세 |
| domestic_stock | inquire_price_2 | /uapi/domestic-stock/v1/quotations/inquire-price-2 | FHPST01010000 | 주식현재가 시세2 |
| domestic_stock | inquire_psbl_order | /uapi/domestic-stock/v1/trading/inquire-psbl-order | TTTC8908R, VTTC8908R | 매수가능조회 |
| domestic_stock | inquire_psbl_rvsecncl | /uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl | TTTC0084R | 주식정정취소가능주문조회 |
| domestic_stock | inquire_psbl_sell | /uapi/domestic-stock/v1/trading/inquire-psbl-sell | TTTC8408R | 매도가능수량조회 |
| domestic_stock | inquire_time_dailychartprice | /uapi/domestic-stock/v1/quotations/inquire-time-dailychartprice | FHKST03010230 | 주식일별분봉조회 |
| domestic_stock | inquire_time_indexchartprice | /uapi/domestic-stock/v1/quotations/inquire-time-indexchartprice | FHKUP03500200 | 업종 분봉조회 |
| domestic_stock | inquire_time_itemchartprice | /uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice | FHKST03010200 | 주식당일분봉조회 |
| domestic_stock | inquire_time_itemconclusion | /uapi/domestic-stock/v1/quotations/inquire-time-itemconclusion | FHPST01060000 | 주식현재가 당일시간대별체결 |
| domestic_stock | inquire_time_overtimeconclusion | /uapi/domestic-stock/v1/quotations/inquire-time-overtimeconclusion | FHPST02310000 | 주식현재가 시간외시간별체결 |
| domestic_stock | inquire_vi_status | /uapi/domestic-stock/v1/quotations/inquire-vi-status | FHPST01390000 | 변동성완화장치(VI) 현황 |
| domestic_stock | intgr_margin | /uapi/domestic-stock/v1/trading/intgr-margin | TTTC0869R | 주식통합증거금 현황 |
| domestic_stock | intstock_grouplist | /uapi/domestic-stock/v1/quotations/intstock-grouplist | HHKCM113004C7 | 관심종목 그룹조회 |
| domestic_stock | intstock_multprice | /uapi/domestic-stock/v1/quotations/intstock-multprice | FHKST11300006 | 관심종목(멀티종목) 시세조회 |
| domestic_stock | intstock_stocklist_by_group | /uapi/domestic-stock/v1/quotations/intstock-stocklist-by-group | HHKCM113004C6 | 관심종목 그룹별 종목조회 |
| domestic_stock | invest_opbysec | /uapi/domestic-stock/v1/quotations/invest-opbysec | FHKST663400C0 | 국내주식 증권사별 투자의견 |
| domestic_stock | invest_opinion | /uapi/domestic-stock/v1/quotations/invest-opinion | FHKST663300C0 | 국내주식 종목투자의견 |
| domestic_stock | investor_program_trade_today | /uapi/domestic-stock/v1/quotations/investor-program-trade-today | HHPPG046600C1 | 프로그램매매 투자자매매동향(당일) |
| domestic_stock | investor_trade_by_stock_daily | /uapi/domestic-stock/v1/quotations/investor-trade-by-stock-daily | FHPTJ04160001 | 종목별 투자자매매동향(일별) |
| domestic_stock | investor_trend_estimate | /uapi/domestic-stock/v1/quotations/investor-trend-estimate | HHPTJ04160200 | 종목별 외인기관 추정가집계 |
| domestic_stock | ksdinfo_bonus_issue | /uapi/domestic-stock/v1/ksdinfo/bonus-issue | HHKDB669101C0 | 예탁원정보(무상증자일정) |
| domestic_stock | ksdinfo_cap_dcrs | /uapi/domestic-stock/v1/ksdinfo/cap-dcrs | HHKDB669106C0 | 예탁원정보(자본감소일정) |
| domestic_stock | ksdinfo_dividend | /uapi/domestic-stock/v1/ksdinfo/dividend | HHKDB669102C0 | 예탁원정보(배당일정) |
| domestic_stock | ksdinfo_forfeit | /uapi/domestic-stock/v1/ksdinfo/forfeit | HHKDB669109C0 | 예탁원정보(실권주일정) |
| domestic_stock | ksdinfo_list_info | /uapi/domestic-stock/v1/ksdinfo/list-info | HHKDB669107C0 | 예탁원정보(상장정보일정) |
| domestic_stock | ksdinfo_mand_deposit | /uapi/domestic-stock/v1/ksdinfo/mand-deposit | HHKDB669110C0 | 예탁원정보(의무예치일정) |
| domestic_stock | ksdinfo_merger_split | /uapi/domestic-stock/v1/ksdinfo/merger-split | HHKDB669104C0 | 예탁원정보(합병_분할일정) |
| domestic_stock | ksdinfo_paidin_capin | /uapi/domestic-stock/v1/ksdinfo/paidin-capin | HHKDB669100C0 | 예탁원정보(유상증자일정) |
| domestic_stock | ksdinfo_pub_offer | /uapi/domestic-stock/v1/ksdinfo/pub-offer | HHKDB669108C0 | 예탁원정보(공모주청약일정) |
| domestic_stock | ksdinfo_purreq | /uapi/domestic-stock/v1/ksdinfo/purreq | HHKDB669103C0 | 예탁원정보(주식매수청구일정) |
| domestic_stock | ksdinfo_rev_split | /uapi/domestic-stock/v1/ksdinfo/rev-split | HHKDB669105C0 | 예탁원정보(액면교체일정) |
| domestic_stock | ksdinfo_sharehld_meet | /uapi/domestic-stock/v1/ksdinfo/sharehld-meet | HHKDB669111C0 | 예탁원정보(주주총회일정) |
| domestic_stock | lendable_by_company | /uapi/domestic-stock/v1/quotations/lendable-by-company | CTSC2702R | 당사 대주가능 종목 |
| domestic_stock | market_cap | /uapi/domestic-stock/v1/ranking/market-cap | FHPST01740000 | 국내주식 시가총액 상위 |
| domestic_stock | market_status_krx | (websocket) | H0STMKO0 | 국내주식 장운영정보 (KRX) |
| domestic_stock | market_status_nxt | (websocket) | H0NXMKO0 | 국내주식 장운영정보(NXT) |
| domestic_stock | market_status_total | (websocket) | H0UNMKO0 | 국내주식 장운영정보(통합) |
| domestic_stock | market_time | /uapi/domestic-stock/v1/quotations/market-time | HHMCM000002C0 | 국내선물 영업일조회 |
| domestic_stock | market_value | /uapi/domestic-stock/v1/ranking/market-value | FHPST01790000 | 국내주식 시장가치 순위 |
| domestic_stock | member_krx | (websocket) | H0STMBC0 | 국내주식 실시간회원사 (KRX) |
| domestic_stock | member_nxt | (websocket) | H0NXMBC0 | 국내주식 실시간회원사 (NXT) |
| domestic_stock | member_total | (websocket) | H0UNMBC0 | 국내주식 실시간회원사 (통합) |
| domestic_stock | mktfunds | /uapi/domestic-stock/v1/quotations/mktfunds | FHKST649100C0 | 국내 증시자금 종합 |
| domestic_stock | near_new_highlow | /uapi/domestic-stock/v1/ranking/near-new-highlow | FHPST01870000 | 국내주식 신고_신저근접종목 상위 |
| domestic_stock | news_title | /uapi/domestic-stock/v1/quotations/news-title | FHKST01011800 | 종합 시황/공시(제목) |
| domestic_stock | order_cash | /uapi/domestic-stock/v1/trading/order-cash | TTTC0011U, TTTC0012U, VTTC0011U, VTTC0012U | 주식주문(현금) |
| domestic_stock | order_credit | /uapi/domestic-stock/v1/trading/order-credit | TTTC0051U, TTTC0052U | 주식주문(신용) |
| domestic_stock | order_resv | /uapi/domestic-stock/v1/trading/order-resv | CTSC0008U | 주식예약주문 |
| domestic_stock | order_resv_ccnl | /uapi/domestic-stock/v1/trading/order-resv-ccnl | CTSC0004R | 주식예약주문조회 |
| domestic_stock | order_resv_rvsecncl | /uapi/domestic-stock/v1/trading/order-resv-rvsecncl | CTSC0009U, CTSC0013U | 주식예약주문정정취소 |
| domestic_stock | order_rvsecncl | /uapi/domestic-stock/v1/trading/order-rvsecncl | TTTC0013U, VTTC0013U | 주식주문(정정취소) |
| domestic_stock | overtime_asking_price_krx | (websocket) | H0STOAA0 | 국내주식 시간외 실시간호가 (KRX) |
| domestic_stock | overtime_ccnl_krx | (websocket) | H0STOUP0 | 국내주식 시간외 실시간체결가 (KRX) |
| domestic_stock | overtime_exp_ccnl_krx | (websocket) | H0STOAC0 | 국내주식 시간외 실시간예상체결 (KRX) |
| domestic_stock | overtime_exp_trans_fluct | /uapi/domestic-stock/v1/ranking/overtime-exp-trans-fluct | FHKST11860000 | 국내주식 시간외예상체결등락률 |
| domestic_stock | overtime_fluctuation | /uapi/domestic-stock/v1/ranking/overtime-fluctuation | FHPST02340000 | 국내주식 시간외등락율순위 |
| domestic_stock | overtime_volume | /uapi/domestic-stock/v1/ranking/overtime-volume | FHPST02350000 | 국내주식 시간외거래량순위 |
| domestic_stock | pbar_tratio | /uapi/domestic-stock/v1/quotations/pbar-tratio | FHPST01130000 | 국내주식 매물대/거래비중 |
| domestic_stock | pension_inquire_balance | /uapi/domestic-stock/v1/trading/pension/inquire-balance | TTTC2208R | 퇴직연금 잔고조회 |
| domestic_stock | pension_inquire_daily_ccld | /uapi/domestic-stock/v1/trading/pension/inquire-daily-ccld | TTTC2201R | 퇴직연금 미체결내역 |
| domestic_stock | pension_inquire_deposit | /uapi/domestic-stock/v1/trading/pension/inquire-deposit | TTTC0506R | 퇴직연금 예수금조회 |
| domestic_stock | pension_inquire_present_balance | /uapi/domestic-stock/v1/trading/pension/inquire-present-balance | TTTC2202R | 퇴직연금 체결기준잔고 |
| domestic_stock | pension_inquire_psbl_order | /uapi/domestic-stock/v1/trading/pension/inquire-psbl-order | TTTC0503R | 퇴직연금 매수가능조회 |
| domestic_stock | period_rights | /uapi/domestic-stock/v1/trading/period-rights | CTRGA011R | 기간별계좌권리현황조회 |
| domestic_stock | prefer_disparate_ratio | /uapi/domestic-stock/v1/ranking/prefer-disparate-ratio | FHPST01770000 | 국내주식 우선주_괴리율 상위 |
| domestic_stock | profit_asset_index | /uapi/domestic-stock/v1/ranking/profit-asset-index | FHPST01730000 | 국내주식 수익자산지표 순위 |
| domestic_stock | program_trade_by_stock | /uapi/domestic-stock/v1/quotations/program-trade-by-stock | FHPPG04650101 | 종목별 프로그램매매추이(체결) |
| domestic_stock | program_trade_by_stock_daily | /uapi/domestic-stock/v1/quotations/program-trade-by-stock-daily | FHPPG04650201 | 종목별 프로그램매매추이(일별) |
| domestic_stock | program_trade_krx | (websocket) | H0STPGM0 | 국내주식 실시간프로그램매매 (KRX) |
| domestic_stock | program_trade_nxt | (websocket) | H0NXPGM0 | 국내주식 실시간프로그램매매 (NXT) |
| domestic_stock | program_trade_total | (websocket) | H0UNPGM0 | 국내주식 실시간프로그램매매 (통합) |
| domestic_stock | psearch_result | /uapi/domestic-stock/v1/quotations/psearch-result | HHKST03900400 | 종목조건검색조회 |
| domestic_stock | psearch_title | /uapi/domestic-stock/v1/quotations/psearch-title | HHKST03900300 | 종목조건검색 목록조회 |
| domestic_stock | quote_balance | /uapi/domestic-stock/v1/ranking/quote-balance | FHPST01720000 | 국내주식 호가잔량 순위 |
| domestic_stock | search_info | /uapi/domestic-stock/v1/quotations/search-info | CTPF1604R | 상품기본조회 |
| domestic_stock | search_stock_info | /uapi/domestic-stock/v1/quotations/search-stock-info | CTPF1002R | 주식기본조회 |
| domestic_stock | short_sale | /uapi/domestic-stock/v1/ranking/short-sale | FHPST04820000 | 국내주식 공매도 상위종목 |
| domestic_stock | top_interest_stock | /uapi/domestic-stock/v1/ranking/top-interest-stock | FHPST01800000 | 국내주식 관심종목등록 상위 |
| domestic_stock | traded_by_company | /uapi/domestic-stock/v1/ranking/traded-by-company | FHPST01860000 | 국내주식 당사매매종목 상위 |
| domestic_stock | tradprt_byamt | /uapi/domestic-stock/v1/quotations/tradprt-byamt | FHKST111900C0 | 국내주식 체결금액별 매매비중 |
| domestic_stock | volume_power | /uapi/domestic-stock/v1/ranking/volume-power | FHPST01680000 | 국내주식 체결강도 상위 |
| domestic_stock | volume_rank | /uapi/domestic-stock/v1/quotations/volume-rank | FHPST01710000 | 거래량순위 |
| elw | compare_stocks | /uapi/elw/v1/quotations/compare-stocks | FHKEW151701C0 |  |
| elw | cond_search | /uapi/elw/v1/quotations/cond-search | FHKEW15100000 |  |
| elw | elw_asking_price | (websocket) | H0EWASP0 |  |
| elw | elw_ccnl | (websocket) | H0EWCNT0 |  |
| elw | elw_exp_ccnl | (websocket) | H0EWANC0 |  |
| elw | expiration_stocks | /uapi/elw/v1/quotations/expiration-stocks | FHKEW154700C0 |  |
| elw | indicator | /uapi/elw/v1/ranking/indicator | FHPEW02790000 |  |
| elw | indicator_trend_ccnl | /uapi/elw/v1/quotations/indicator-trend-ccnl | FHPEW02740100 |  |
| elw | indicator_trend_daily | /uapi/elw/v1/quotations/indicator-trend-daily | FHPEW02740200 |  |
| elw | indicator_trend_minute | /uapi/elw/v1/quotations/indicator-trend-minute | FHPEW02740300 |  |
| elw | lp_trade_trend | /uapi/elw/v1/quotations/lp-trade-trend | FHPEW03760000 |  |
| elw | newly_listed | /uapi/elw/v1/quotations/newly-listed | FHKEW154800C0 |  |
| elw | quick_change | /uapi/elw/v1/ranking/quick-change | FHPEW02870000 |  |
| elw | sensitivity | /uapi/elw/v1/ranking/sensitivity | FHPEW02850000 |  |
| elw | sensitivity_trend_ccnl | /uapi/elw/v1/quotations/sensitivity-trend-ccnl | FHPEW02830100 |  |
| elw | sensitivity_trend_daily | /uapi/elw/v1/quotations/sensitivity-trend-daily | FHPEW02830200 |  |
| elw | udrl_asset_list | /uapi/elw/v1/quotations/udrl-asset-list | FHKEW154100C0 |  |
| elw | udrl_asset_price | /uapi/elw/v1/quotations/udrl-asset-price | FHKEW154101C0 |  |
| elw | updown_rate | /uapi/elw/v1/ranking/updown-rate | FHPEW02770000 |  |
| elw | volatility_trend_ccnl | /uapi/elw/v1/quotations/volatility-trend-ccnl | FHPEW02840100 |  |
| elw | volatility_trend_daily | /uapi/elw/v1/quotations/volatility-trend-daily | FHPEW02840200 |  |
| elw | volatility_trend_minute | /uapi/elw/v1/quotations/volatility-trend-minute | FHPEW02840300 |  |
| elw | volatility_trend_tick | /uapi/elw/v1/quotations/volatility-trend-tick | FHPEW02840400 |  |
| elw | volume_rank | /uapi/elw/v1/ranking/volume-rank | FHPEW02780000 |  |
| etfetn | etf_nav_trend | (websocket) | H0STNAV0 | 국내ETF NAV추이 |
| etfetn | inquire_component_stock_price | /uapi/etfetn/v1/quotations/inquire-component-stock-price | FHKST121600C0 | ETF 구성종목시세 |
| etfetn | inquire_price | /uapi/etfetn/v1/quotations/inquire-price | FHPST02400000 | ETF/ETN 현재가 |
| etfetn | nav_comparison_daily_trend | /uapi/etfetn/v1/quotations/nav-comparison-daily-trend | FHPST02440200 | NAV 비교추이(일) |
| etfetn | nav_comparison_time_trend | /uapi/etfetn/v1/quotations/nav-comparison-time-trend | FHPST02440100 | NAV 비교추이(분) |
| etfetn | nav_comparison_trend | /uapi/etfetn/v1/quotations/nav-comparison-trend | FHPST02440000 | NAV 비교추이(종목) |
| overseas_futureoption | asking_price | (websocket) | HDFFF010 | 해외선물옵션 실시간호가 |
| overseas_futureoption | ccnl | (websocket) | HDFFF020 | 해외선물옵션 실시간체결가 |
| overseas_futureoption | ccnl_notice | (websocket) | HDFFF2C0 | 해외선물옵션 실시간체결내역통보 |
| overseas_futureoption | daily_ccnl | /uapi/overseas-futureoption/v1/quotations/daily-ccnl | HHDFC55020100 | 해외선물 체결추이(일간) |
| overseas_futureoption | inquire_asking_price | /uapi/overseas-futureoption/v1/quotations/inquire-asking-price | HHDFC86000000 | 해외선물 호가 |
| overseas_futureoption | inquire_ccld | /uapi/overseas-futureoption/v1/trading/inquire-ccld |  | 해외선물옵션 당일주문내역조회 |
| overseas_futureoption | inquire_daily_ccld | /uapi/overseas-futureoption/v1/trading/inquire-daily-ccld |  | 해외선물옵션 일별체결내역 |
| overseas_futureoption | inquire_daily_order | /uapi/overseas-futureoption/v1/trading/inquire-daily-order |  | 해외선물옵션 일별 주문내역 |
| overseas_futureoption | inquire_deposit | /uapi/overseas-futureoption/v1/trading/inquire-deposit |  | 해외선물옵션 예수금현황 |
| overseas_futureoption | inquire_period_ccld | /uapi/overseas-futureoption/v1/trading/inquire-period-ccld |  | 해외선물옵션 기간계좌손익 일별 |
| overseas_futureoption | inquire_period_trans | /uapi/overseas-futureoption/v1/trading/inquire-period-trans |  | 해외선물옵션 기간계좌거래내역 |
| overseas_futureoption | inquire_price | /uapi/overseas-futureoption/v1/quotations/inquire-price | HHDFC55010000 | 해외선물종목현재가 |
| overseas_futureoption | inquire_psamount | /uapi/overseas-futureoption/v1/trading/inquire-psamount |  | 해외선물옵션 주문가능조회 |
| overseas_futureoption | inquire_time_futurechartprice | /uapi/overseas-futureoption/v1/quotations/inquire-time-futurechartprice | HHDFC55020400 | 해외선물 분봉조회 |
| overseas_futureoption | inquire_time_optchartprice | /uapi/overseas-futureoption/v1/quotations/inquire-time-optchartprice | HHDFO55020100 | 해외옵션 분봉조회 |
| overseas_futureoption | inquire_unpd | /uapi/overseas-futureoption/v1/trading/inquire-unpd |  | 해외선물옵션 미결제내역조회(잔고) |
| overseas_futureoption | investor_unpd_trend | /uapi/overseas-futureoption/v1/quotations/investor-unpd-trend | HHDDB95030000 | 해외선물 미결제추이 |
| overseas_futureoption | margin_detail | /uapi/overseas-futureoption/v1/trading/margin-detail |  | 해외선물옵션 증거금상세 |
| overseas_futureoption | market_time | /uapi/overseas-futureoption/v1/quotations/market-time |  | 해외선물옵션 장운영시간 |
| overseas_futureoption | monthly_ccnl | /uapi/overseas-futureoption/v1/quotations/monthly-ccnl | HHDFC55020300 | 해외선물 체결추이(월간) |
| overseas_futureoption | opt_asking_price | /uapi/overseas-futureoption/v1/quotations/opt-asking-price | HHDFO86000000 | 해외옵션 호가 |
| overseas_futureoption | opt_daily_ccnl | /uapi/overseas-futureoption/v1/quotations/opt-daily-ccnl | HHDFO55020100 | 해외옵션 체결추이(일간) |
| overseas_futureoption | opt_detail | /uapi/overseas-futureoption/v1/quotations/opt-detail | HHDFO55010100 | 해외옵션종목상세 |
| overseas_futureoption | opt_monthly_ccnl | /uapi/overseas-futureoption/v1/quotations/opt-monthly-ccnl | HHDFO55020300 | 해외옵션 체결추이(월간) |
| overseas_futureoption | opt_price | /uapi/overseas-futureoption/v1/quotations/opt-price | HHDFO55010000 | 해외옵션종목현재가 |
| overseas_futureoption | opt_tick_ccnl | /uapi/overseas-futureoption/v1/quotations/opt-tick-ccnl | HHDFO55020200 | 해외옵션 체결추이(틱) |
| overseas_futureoption | opt_weekly_ccnl | /uapi/overseas-futureoption/v1/quotations/opt-weekly-ccnl | HHDFO55020000 | 해외옵션 체결추이(주간) |
| overseas_futureoption | order | /uapi/overseas-futureoption/v1/trading/order |  | 해외선물옵션 주문 |
| overseas_futureoption | order_notice | (websocket) | HDFFF1C0 | 해외선물옵션 실시간주문내역통보 |
| overseas_futureoption | order_rvsecncl | /uapi/overseas-futureoption/v1/trading/order-rvsecncl |  | 해외선물옵션 정정취소주문 |
| overseas_futureoption | search_contract_detail | /uapi/overseas-futureoption/v1/quotations/search-contract-detail | HHDFC55200000 | 해외선물 상품기본정보 |
| overseas_futureoption | search_opt_detail | /uapi/overseas-futureoption/v1/quotations/search-opt-detail | HHDFO55200000 | 해외옵션 상품기본정보 |
| overseas_futureoption | stock_detail | /uapi/overseas-futureoption/v1/quotations/stock-detail | HHDFC55010100 | 해외선물종목상세 |
| overseas_futureoption | tick_ccnl | /uapi/overseas-futureoption/v1/quotations/tick-ccnl | HHDFC55020200 | 해외선물 체결추이(틱) |
| overseas_futureoption | weekly_ccnl | /uapi/overseas-futureoption/v1/quotations/weekly-ccnl | HHDFC55020000 | 해외선물 체결추이(주간) |
| overseas_stock | algo_ordno | /uapi/overseas-stock/v1/trading/algo-ordno | TTTS6058R | 해외주식 지정가주문번호조회 |
| overseas_stock | asking_price | (websocket) | HDFSASP0 | 해외주식 실시간호가 |
| overseas_stock | brknews_title | /uapi/overseas-price/v1/quotations/brknews-title | FHKST01011801 | 해외속보(제목) |
| overseas_stock | ccnl_notice | (websocket) | H0GSCNI0, H0GSCNI9 | 해외주식 실시간체결통보 |
| overseas_stock | colable_by_company | /uapi/overseas-price/v1/quotations/colable-by-company | CTLN4050R | 당사 해외주식담보대출 가능 종목 |
| overseas_stock | countries_holiday | /uapi/overseas-stock/v1/quotations/countries-holiday | CTOS5011R | 해외결제일자조회 |
| overseas_stock | dailyprice | /uapi/overseas-price/v1/quotations/dailyprice | HHDFS76240000 | 해외주식 기간별시세 |
| overseas_stock | daytime_order | /uapi/overseas-stock/v1/trading/daytime-order | TTTS6036U, TTTS6037U | 해외주식 미국주간주문 |
| overseas_stock | daytime_order_rvsecncl | /uapi/overseas-stock/v1/trading/daytime-order-rvsecncl | TTTS6038U | 해외주식 미국주간정정취소 |
| overseas_stock | delayed_asking_price_asia | (websocket) | HDFSASP1 | 해외주식 지연호가(아시아) |
| overseas_stock | delayed_ccnl | (websocket) | HDFSCNT0 | 해외주식 실시간지연체결가 |
| overseas_stock | foreign_margin | /uapi/overseas-stock/v1/trading/foreign-margin | TTTC2101R |  |
| overseas_stock | industry_price | /uapi/overseas-price/v1/quotations/industry-price | HHDFS76370100 | 해외주식 업종별코드조회 |
| overseas_stock | industry_theme | /uapi/overseas-price/v1/quotations/industry-theme | HHDFS76370000 | 해외주식 업종별시세 |
| overseas_stock | inquire_algo_ccnl | /uapi/overseas-stock/v1/trading/inquire-algo-ccnl | TTTS6059R | 해외주식 지정가체결내역조회 |
| overseas_stock | inquire_asking_price | /uapi/overseas-price/v1/quotations/inquire-asking-price | HHDFS76200100 | 해외주식 현재가 1호가 |
| overseas_stock | inquire_balance | /uapi/overseas-stock/v1/trading/inquire-balance | TTTS3012R, VTTS3012R | 해외주식 잔고 |
| overseas_stock | inquire_ccnl | /uapi/overseas-stock/v1/trading/inquire-ccnl | TTTS3035R, VTTS3035R | 해외주식 주문체결내역 |
| overseas_stock | inquire_daily_chartprice | /uapi/overseas-price/v1/quotations/inquire-daily-chartprice | FHKST03030100 | 해외주식 종목_지수_환율기간별시세(일_주_월_년) |
| overseas_stock | inquire_nccs | /uapi/overseas-stock/v1/trading/inquire-nccs | TTTS3018R | 해외주식 미체결내역 |
| overseas_stock | inquire_paymt_stdr_balance | /uapi/overseas-stock/v1/trading/inquire-paymt-stdr-balance | CTRP6010R | 해외주식 결제기준잔고 |
| overseas_stock | inquire_period_profit | /uapi/overseas-stock/v1/trading/inquire-period-profit | TTTS3039R | 해외주식 기간손익 |
| overseas_stock | inquire_period_trans | /uapi/overseas-stock/v1/trading/inquire-period-trans | CTOS4001R | 해외주식 일별거래내역 |
| overseas_stock | inquire_present_balance | /uapi/overseas-stock/v1/trading/inquire-present-balance | CTRP6504R, VTRP6504R | 해외주식 체결기준현재잔고 |
| overseas_stock | inquire_psamount | /uapi/overseas-stock/v1/trading/inquire-psamount | TTTS3007R, VTTS3007R | 해외주식 매수가능금액조회 |
| overseas_stock | inquire_search | /uapi/overseas-price/v1/quotations/inquire-search | HHDFS76410000 | 해외주식조건검색 |
| overseas_stock | inquire_time_indexchartprice | /uapi/overseas-price/v1/quotations/inquire-time-indexchartprice | FHKST03030200 | 해외지수분봉조회 |
| overseas_stock | inquire_time_itemchartprice | /uapi/overseas-price/v1/quotations/inquire-time-itemchartprice | HHDFS76950200 | 해외주식분봉조회 |
| overseas_stock | market_cap | /uapi/overseas-stock/v1/ranking/market-cap | HHDFS76350100 | 해외주식 시가총액순위 |
| overseas_stock | new_highlow | /uapi/overseas-stock/v1/ranking/new-highlow | HHDFS76300000 | 해외주식 신고/신저가 |
| overseas_stock | news_title | /uapi/overseas-price/v1/quotations/news-title | HHPSTH60100C1 | 해외뉴스종합(제목) |
| overseas_stock | order | /uapi/overseas-stock/v1/trading/order | TTTS0202U, TTTS0304U, TTTS0305U, TTTS0307U, TTTS0308U, TTTS0310U, TTTS0311U, TTTS1001U, TTTS1002U, TTTS1005U, TTTT1002U, TTTT1006U | 해외주식 주문 |
| overseas_stock | order_resv | /uapi/overseas-stock/v1/trading/order-resv | TTTS3013U, TTTT3014U, TTTT3016U, VTTS3013U, VTTT3014U, VTTT3016U | 해외주식 예약주문접수 |
| overseas_stock | order_resv_ccnl | /uapi/overseas-stock/v1/trading/order-resv-ccnl | TTTT3017U, VTTT3017U | 해외주식 예약주문접수취소 |
| overseas_stock | order_resv_list | /uapi/overseas-stock/v1/trading/order-resv-list | TTTS3014R, TTTT3039R | 해외주식 예약주문조회 |
| overseas_stock | order_rvsecncl | /uapi/overseas-stock/v1/trading/order-rvsecncl | TTTT1004U, VTTT1004U | 해외주식 정정취소주문 |
| overseas_stock | period_rights | /uapi/overseas-price/v1/quotations/period-rights | CTRGT011R | 해외주식 기간별권리조회 |
| overseas_stock | price | /uapi/overseas-price/v1/quotations/price | HHDFS00000300 | 해외주식 현재체결가 |
| overseas_stock | price_detail | /uapi/overseas-price/v1/quotations/price-detail | HHDFS76200200 | 해외주식 현재가상세 |
| overseas_stock | price_fluct | /uapi/overseas-stock/v1/ranking/price-fluct | HHDFS76260000 | 해외주식 가격급등락 |
| overseas_stock | quot_inquire_ccnl | /uapi/overseas-price/v1/quotations/inquire-ccnl | HHDFS76200300 | 해외주식 체결추이 |
| overseas_stock | rights_by_ice | /uapi/overseas-price/v1/quotations/rights-by-ice | HHDFS78330900 | 해외주식 권리종합 |
| overseas_stock | search_info | /uapi/overseas-price/v1/quotations/search-info | CTPF1702R | 해외주식 상품기본정보 |
| overseas_stock | trade_growth | /uapi/overseas-stock/v1/ranking/trade-growth | HHDFS76330000 | 해외주식 거래증가율순위 |
| overseas_stock | trade_pbmn | /uapi/overseas-stock/v1/ranking/trade-pbmn | HHDFS76320010 | 해외주식 거래대금순위 |
| overseas_stock | trade_turnover | /uapi/overseas-stock/v1/ranking/trade-turnover | HHDFS76340000 | 해외주식 거래회전율순위 |
| overseas_stock | trade_vol | /uapi/overseas-stock/v1/ranking/trade-vol | HHDFS76310010 | 해외주식 거래량순위 |
| overseas_stock | updown_rate | /uapi/overseas-stock/v1/ranking/updown-rate | HHDFS76290000 | 해외주식 상승률/하락률 |
| overseas_stock | volume_power | /uapi/overseas-stock/v1/ranking/volume-power | HHDFS76280000 | 해외주식 매수체결강도상위 |
| overseas_stock | volume_surge | /uapi/overseas-stock/v1/ranking/volume-surge | HHDFS76270000 | 해외주식 거래량급증 |
