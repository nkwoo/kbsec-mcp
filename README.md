# KB증권 OpenAPI MCP 서버

KB증권 OpenAPI 74개 엔드포인트(시세, 주문, 계좌, 투자정보 — 국내·해외주식)를 감싸는 Python MCP
서버입니다. Claude Desktop, Claude Code 등 MCP 클라이언트에서 이 서버를 등록하면 자연어로 시세
조회, 주문, 계좌 조회 등을 수행할 수 있습니다.

## ⚠️ 사용 전 필수 확인사항

이 프로젝트는 KB증권이 공식 지원하지 않는 **비공식 개인 프로젝트**입니다. 아래 내용을 반드시
읽고 본인 책임 하에 사용하세요.

- **실제 계좌와 실거래를 다룹니다.** 이 서버가 노출하는 도구 중 일부는 실제 매수/매도 주문
  접수·정정·취소를 수행합니다. 잘못된 파라미터, 프롬프트에 대한 오해, LLM의 실수 등으로 발생하는
  손실을 포함해 **이 서버 사용으로 인한 모든 결과(금전적 손실 포함)에 대한 책임은 전적으로
  사용자 본인에게 있습니다.**
- **appKey/appSecret은 실거래 권한을 가진 민감 정보입니다.** `.env` 파일에만 보관하고 git에
  커밋하거나 외부에 공유하지 마세요.
- **로컬 IP·MAC 주소가 KB증권 서버로 전송됩니다.** KB증권 API 규격상 모든 요청 바디에
  `dataHeader.ipAddr`/`dataHeader.macAddr`를 포함해야 하며, 이 서버는 `client.py`에서 로컬
  네트워크 인터페이스로부터 이 값을 자동으로 조회해 매 API 호출마다 KB증권 서버로 전송합니다.
- **응답 성공/실패는 HTTP 상태 코드로만 판별합니다.** KB증권 API는 공식 에러 코드 체계를
  문서화하지 않아, HTTP 200이지만 비즈니스 로직상 실패(예: 잔고 부족으로 주문 거부)인 경우
  응답 JSON의 `msg`/`o_msg` 필드를 직접 확인해야 합니다.
- API 파라미터·응답 필드의 정확한 의미, 최신 정책, rate limit 등 최종 기준은 이 README가 아닌
  **KB증권 오픈API 공식 문서(https://openapi.kbsec.com/apidoc_b2c)** 입니다.

## 설치

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

개발/테스트를 진행하려면 대신 `pip install -r requirements-dev.txt`를 사용하세요 (pytest 포함).

## .env 설정

`.env.example`을 복사해 `.env`를 만들고 KB증권 개발자센터에서 발급받은 값을 채워 넣으세요.

```bash
cp .env.example .env
```

| 변수 | 필수 여부 | 설명 |
|---|---|---|
| `KBSEC_APP_KEY` | 필수 | KB증권 개발자센터에서 발급받은 appKey |
| `KBSEC_APP_SECRET` | 필수 | KB증권 개발자센터에서 발급받은 appSecret |
| `KBSEC_BASE_URL` | 선택 (기본값 `https://developer.kbsec.com:32484`) | API 서버 주소 |
| `KBSEC_TIMEOUT_SECONDS` | 선택 (기본값 `10`) | HTTP 요청 타임아웃(초) |

`appKey`/`appSecret`/토큰은 코드나 로그에 절대 기록되지 않으며, 프로세스 메모리에만 보관됩니다.

## 실행 확인

```bash
python server.py
```

정상 기동하면 stdio로 MCP 클라이언트의 연결을 기다립니다 (Ctrl+C로 종료).

## Claude Desktop / Claude Code 등록

`claude_desktop_config.json`(Claude Desktop) 또는 프로젝트의 MCP 설정 파일에 아래 스니펫을
추가하세요. `command`/`args`의 경로는 실제 설치 경로에 맞게 절대경로로 바꿔주세요.

```json
{
  "mcpServers": {
    "kbsec": {
      "command": "/absolute/path/to/KBSec_MCP_Server/.venv/bin/python",
      "args": ["/absolute/path/to/KBSec_MCP_Server/server.py"]
    }
  }
}
```

`.env`는 `server.py`와 같은 디렉터리에서 자동으로 로드되므로 `env` 필드에 별도로 키를 넣을
필요는 없습니다 (다만 넣고 싶다면 `"env": {"KBSEC_APP_KEY": "...", "KBSEC_APP_SECRET": "..."}` 형태로
추가해도 동작합니다 — `.env` 값보다 우선 적용됩니다).

## 전체 도구(Tool) 목록

74개 도구는 카테고리 접두사로 그룹화되어 있습니다: `quote_kr_`(국내 기본시세),
`ranking_kr_`(국내 시세분석), `order_kr_`(국내 주식주문), `account_kr_`(국내 계좌잔고),
`orderhist_kr_`(국내 주문내역), `market_kr_`(국내 투자정보), `quote_os_`(해외 기본시세),
`account_os_`(해외 계좌잔고), `order_os_`(해외 주식주문), `orderhist_os_`(해외 주문내역),
`ranking_os_`(해외 시세분석).

| Tool 이름 | KB증권 API | 설명 |
|---|---|---|
| `quote_kr_get_orderbook` | IVU10070 | 종목 호가 정보 조회 |
| `quote_kr_get_time_trades` | IVU10080 | 시간대별 체결(틱) 조회 |
| `quote_kr_get_price` | IVU10140 | 현재가 조회 (재무/투자지표 포함) |
| `quote_kr_get_broker_trend` | IVU10420 | 당일 주요 외국계 거래원 조회 |
| `quote_kr_get_investor_trend` | IVU10430 | 투자자별(기관/외국인/개인) 매매동향 조회 |
| `quote_kr_get_program_trading` | IVU10450 | 프로그램매매 동향 조회 |
| `quote_kr_get_stock_info` | SIQM4900 | 종목 기본정보 단건 조회 |
| `quote_kr_get_market_status` | SZQM0771 | 장운영상태 조회 |
| `quote_kr_get_company_overview` | IVM10050 | 기업개요 조회 |
| `quote_kr_get_chart` | IVS11560 | 통합차트(일/분봉 등) 조회 |
| `ranking_kr_get_top_trading_value` | IVU10210 | ATS통합 거래대금 상위 |
| `ranking_kr_get_top_change_rate` | IVU10240 | 전일대비 등락률 상위 |
| `ranking_kr_get_top_price_surge_drop` | IVU10270 | 가격 급등/급락 종목 |
| `ranking_kr_get_top_volume` | IVU10280 | 당일 거래량 상위 |
| `ranking_kr_get_new_high_low` | IVU10550 | 신고가/신저가 |
| `ranking_kr_get_top_open_price_change` | IVS10910 | 시가대비 등락률 상위 |
| `ranking_kr_get_top_market_cap` | IVS10920 | 시가총액 상위 |
| `ranking_kr_get_top_after_hours_change` | IVS11190 | 시간외단일가 등락률 순위 |
| `ranking_kr_get_top_foreign_institution_trading` | IVU10020 | 외국인/기관 매매 상위 |
| `order_kr_place_reserve_order` | SSAM0831 | 예약주문 접수(현금/신용 통합) |
| `order_kr_place_sell_order` | SSAM1801 | 현금 매도 주문 접수 |
| `order_kr_place_buy_order` | SSAM1802 | 현금 매수 주문 접수 |
| `order_kr_amend_order` | SSAM1805 | 미체결 주문 정정 |
| `order_kr_cancel_order` | SSAM1806 | 미체결 주문 취소 |
| `order_kr_place_fractional_sell_order` | SSAM5762 | 소수점 매도 주문 접수 |
| `order_kr_place_fractional_buy_order` | SSAM5763 | 소수점 매수 주문 접수 |
| `order_kr_cancel_fractional_order` | SSAM5764 | 소수점 주문 취소 |
| `order_kr_get_buyable_amount` | SSQM1802 | 매수 가능 금액/수량 조회 |
| `account_kr_get_deposit_details` | SSQM0004 | 예수금 내역 조회 |
| `account_kr_get_holdings` | SSQM1801 | 보유주식 목록/상세 조회 |
| `account_kr_get_settlement_status` | SSQM2121 | 매매정산현황 조회 |
| `account_kr_get_trading_profit_loss` | SSQM2392 | 기간별 매매손익현황 조회 |
| `account_kr_get_realized_profit_loss` | SSQM2442 | 일자별 실현손익 조회 |
| `account_kr_get_balance_settlement_basis` | SSQM2932 | 잔고현황(결제기준) 조회 |
| `account_kr_get_balance_trade_basis` | SSQM2952 | 잔고현황(체결기준)/총자산평가 조회 |
| `account_kr_get_transaction_history` | SWQA2301 | 계좌 거래내역(입출금/매매/배당) 조회 |
| `account_kr_get_transaction_history_detail` | SWQM2412 | 거래내역 상세 조회 |
| `account_kr_get_withdrawable_amount` | SWQN2302 | D+1/D+2 출금가능금액 조회 |
| `orderhist_kr_get_reserve_order_result` | SSQM0831 | 예약주문 처리결과 조회 |
| `orderhist_kr_get_reserve_order_list` | SSQM0834 | 예약주문 접수내역 조회 |
| `orderhist_kr_get_order_execution_status` | SSQM2341 | 주문 체결/미체결 내역 조회 |
| `orderhist_kr_get_fractional_trade_history` | SSQM5765 | 소수점 매매 전체 내역 조회 |
| `market_kr_get_market_liquidity_trend` | IVA10370 | 증시주변자금동향 조회 |
| `market_kr_get_world_indices` | IVA60140 | 세계지수 조회 |
| `market_kr_get_exchange_rates` | IVA60190 | 환율종합 조회 |
| `market_kr_get_sector_ranking` | IVM30010 | 업종랭킹(MTS) 조회 |
| `market_kr_get_market_summary` | IVSA0070 | 시장종합 조회 |
| `quote_os_get_stock_info` | SIAM4983 | 해외주식 종목정보 조회 |
| `quote_os_get_price` | GSS10030 | 현재가 조회 |
| `quote_os_get_orderbook` | GSS10040 | 호가 조회 |
| `quote_os_get_time_trades` | GSA10020 | 시간대별 체결 조회 |
| `quote_os_get_chart` | GSC10060 | 통합차트 조회 |
| `account_os_get_settlement_status` | SPQM2205 | 매매정산 현황 조회 |
| `account_os_get_daily_profit_loss` | SPQM2206 | 당일 매매손익 조회 |
| `account_os_get_period_profit_loss` | SPQM2207 | 기간별 매매손익 조회 |
| `account_os_get_margin` | SPQM3390 | 글로벌원마켓 통합증거금 사용현황 조회 |
| `account_os_get_balance` | SPQM2226 | 해외주식 계좌 잔고평가 조회 |
| `account_os_get_corporate_actions` | SRQM3051 | 배당/무상증자 등 권리발생내역 조회 |
| `order_os_get_buyable_amount` | SKQM2106 | 통화별 주문가능금액 조회 |
| `order_os_get_buyable_amount_status` | SKQM3350 | 통화별 주문가능 예수금 현황 조회 |
| `order_os_place_order` | SKAM2101 | 매도/매수 주문 접수 |
| `order_os_amend_cancel_order` | SKAM2102 | 주문 정정/취소 |
| `order_os_get_fractional_buyable_amount` | SPQN5472 | 소수점 매매 주문가능금액 조회 |
| `order_os_place_fractional_order` | SKAM2201 | 소수점 매도/매수 주문 접수 |
| `order_os_cancel_fractional_order` | SKAM2202 | 소수점 주문 취소 |
| `order_os_place_us_reserve_order` | SPAO2104 | 미국주식 예약주문 접수 |
| `order_os_cancel_us_reserve_order` | SPAO2106 | 미국주식 예약주문 취소 |
| `orderhist_os_get_execution_history` | SPQM2103 | 주문 체결내역 조회 |
| `orderhist_os_get_execution_status` | SPQM2204 | 당일 체결/미체결 현황 조회 |
| `orderhist_os_get_reserve_order_list` | SPQO2105 | 예약주문 조회 |
| `ranking_os_get_market_analysis` | GSA10600 | 해외시세분석 |
| `ranking_os_get_top_volume` | GSA10150 | 거래량 상위 |
| `ranking_os_get_top_market_cap` | GSA10170 | 시가총액 상위 |
| `ranking_os_get_new_high_low` | GSS10180 | 신고/신저 조회 |

각 도구의 응답(OUTPUT) 필드는 KB증권 API가 반환한 JSON을 그대로 전달합니다 (필드가 많게는
100개 이상이라 도구 설명에는 포함하지 않았습니다). 필드별 의미는 KB증권 오픈API 공식 문서를
참고하세요.
