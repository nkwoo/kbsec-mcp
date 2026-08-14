# KB증권 OpenAPI MCP 서버

KB증권 OpenAPI 74개 엔드포인트(시세, 주문, 계좌, 투자정보 — 국내·해외주식)에 토큰 폐기 도구
1개를 더해 총 75개 도구로 감싸는 Python MCP 서버입니다. Claude Desktop, Claude Code 등 MCP
클라이언트에서 이 서버를 등록하면 자연어로 시세 조회, 주문, 계좌 조회 등을 수행할 수 있습니다.

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
- **실거래 도구는 기본적으로 차단되어 있습니다.** `KBSEC_ENABLE_TRADING=true`를 명시적으로
  설정하기 전까지는 주문 접수/정정/취소가 실행되지 않습니다 (아래 "실거래 안전장치" 참고).
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
| `KBSEC_ENABLE_TRADING` | 선택 (기본값 `false`) | 실거래(주문 접수/정정/취소) 도구 활성화 여부. 아래 "실거래 안전장치" 참고 |

`appKey`/`appSecret`/토큰은 코드나 로그에 절대 기록되지 않으며, 프로세스 메모리에만 보관됩니다.

## 실거래 안전장치

74개 도구 중 **실제로 주문을 접수·정정·취소하는 14개 도구**(`order_kr_place_*`,
`order_kr_amend_order`, `order_kr_cancel_*`, `order_os_place_*`, `order_os_amend_cancel_order`,
`order_os_cancel_*`)는 `KBSEC_ENABLE_TRADING`이 `true`(또는 `1`/`yes`/`on`, 대소문자 무관)로
설정되지 않으면 **기본적으로 차단**됩니다. 차단된 상태에서 호출하면 KB증권 API에 실제 요청을
보내지 않고 즉시 아래와 같은 에러를 반환합니다.

```
실거래 도구 호출이 차단되었습니다 (/api/v1/ssam1801). 활성화하려면 .env에 KBSEC_ENABLE_TRADING=true를 설정하세요.
```

매수가능금액 조회처럼 실제 주문을 넣지 않는 나머지 4개 도구(`order_kr_get_buyable_amount`,
`order_os_get_buyable_amount`, `order_os_get_buyable_amount_status`,
`order_os_get_fractional_buyable_amount`)는 이 안전장치와 무관하게 항상 사용할 수 있습니다.

실거래를 허용하려면 `.env`에 다음 줄을 추가하세요:

```
KBSEC_ENABLE_TRADING=true
```

## 실행 확인

```bash
python server.py
```

정상 기동하면 stdio로 MCP 클라이언트의 연결을 기다립니다 (Ctrl+C로 종료).

## MCP 클라이언트 등록

이 서버는 표준 MCP(stdio) 프로토콜을 그대로 구현하므로 Claude 외에도 MCP를 지원하는 어떤
클라이언트에서도 동일하게 사용할 수 있습니다. 아래에서 사용 중인 클라이언트에 맞는 설정을 골라
추가하세요. `command`/`args`의 경로는 실제 설치 경로에 맞게 절대경로로 바꿔주세요.

`.env`는 `server.py`와 같은 디렉터리에서 자동으로 로드되므로 클라이언트 설정에 별도로 키를
넣을 필요는 없습니다 (다만 넣고 싶다면 클라이언트별 `env` 필드에 `KBSEC_APP_KEY`/
`KBSEC_APP_SECRET` 등을 추가해도 동작합니다 — `.env` 값보다 우선 적용됩니다).

### Claude Desktop / Claude Code

`claude_desktop_config.json`(Claude Desktop) 또는 프로젝트의 `.mcp.json`(Claude Code)에 아래
스니펫을 추가하세요.

```json
{
  "mcpServers": {
    "kbsec": {
      "command": "/absolute/path/to/kbsec-mcp/.venv/bin/python",
      "args": ["/absolute/path/to/kbsec-mcp/server.py"]
    }
  }
}
```

`.env` 파일 대신 설정 JSON에서 직접 환경변수를 넘기고 싶다면 `env` 필드를 추가하세요. 이 값은
`.env` 값보다 우선 적용됩니다.

```json
{
  "mcpServers": {
    "kbsec": {
      "command": "/absolute/path/to/kbsec-mcp/.venv/bin/python",
      "args": ["/absolute/path/to/kbsec-mcp/server.py"],
      "env": {
        "KBSEC_APP_KEY": "your_app_key",
        "KBSEC_APP_SECRET": "your_app_secret"
      }
    }
  }
}
```

Claude Code는 `claude mcp add` 명령으로도 등록할 수 있고, `-e`(`--env`) 플래그로 `KBSEC_APP_KEY`
같은 환경변수를 함께 넘길 수 있습니다 (플래그는 반복 지정 가능하며, `--` 뒤에 실행할 명령을
씁니다).

```bash
claude mcp add kbsec \
  -e KBSEC_APP_KEY=your_app_key \
  -e KBSEC_APP_SECRET=your_app_secret \
  -- /absolute/path/to/kbsec-mcp/.venv/bin/python /absolute/path/to/kbsec-mcp/server.py
```

기본 스코프는 `local`(현재 프로젝트에만 적용)입니다. 여러 프로젝트에서 공용으로 쓰려면
`-s user`(사용자 전역), 프로젝트 팀원과 설정을 공유하려면 `-s project`를 추가하세요. 이 방식으로
넘긴 값은 `.env` 값보다 우선 적용됩니다.

### 그 외 MCP 클라이언트

Claude Desktop / Claude Code 외에도 stdio 기반 MCP 서버 등록을 지원하는 클라이언트라면 대부분
`command`(파이썬 실행 파일 경로)와 `args`(`server.py` 절대경로) 두 값만 지정하면 됩니다. 정확한
설정 파일 위치와 스키마는 사용 중인 클라이언트의 공식 문서를 확인하세요.

## 전체 도구(Tool) 목록

74개의 시세/주문/계좌/투자정보 도구는 KB증권 OpenAPI 명세
(`spec/source/kbsec-openapi.postman_collection.json`)와 동일한 국내주식/해외주식 카테고리
구조로 정리되어 있습니다. 여기에 인증 관련 도구 1개(`auth_revoke_token`)가 더해져 총 75개입니다.
각 도구가 받는 파라미터 상세는 `spec/kbsec_api_spec.json`을 참고하세요.

### 인증

KB증권 API는 access token 값과 함께 발급 당시의 IP/MAC 주소를 검증합니다. 네트워크 환경이
바뀌어(VPN 연결, Wi-Fi 전환 등) 캐시된 토큰의 IP/MAC이 더 이상 일치하지 않으면, 만료 전이라도
모든 API 호출이 검증 실패로 거부될 수 있습니다. 이때 아래 도구로 캐시된 토큰을 강제로 폐기하면
다음 호출에서 현재 IP/MAC 기준으로 새 토큰이 재발급됩니다 (토큰 발급 자체는 모든 도구 호출 시
자동으로 처리되므로 별도 도구가 없습니다).

| 설명 | Tool 이름 | KB증권 API |
|---|---|---|
| 캐시된 access token 폐기 (다음 호출에서 재발급 강제) | `auth_revoke_token` | oauth2/revoke |

### 국내 주식

#### 기본시세

| 설명 | Tool 이름 | KB증권 API |
|---|---|---|
| 종목 호가 정보 조회 | `quote_kr_get_orderbook` | IVU10070 |
| 시간대별 체결(틱) 조회 | `quote_kr_get_time_trades` | IVU10080 |
| 현재가 조회 (재무/투자지표 포함) | `quote_kr_get_price` | IVU10140 |
| 당일 주요 외국계 거래원 조회 | `quote_kr_get_broker_trend` | IVU10420 |
| 투자자별(기관/외국인/개인) 매매동향 조회 | `quote_kr_get_investor_trend` | IVU10430 |
| 프로그램매매 동향 조회 | `quote_kr_get_program_trading` | IVU10450 |
| 종목 기본정보 단건 조회 | `quote_kr_get_stock_info` | SIQM4900 |
| 장운영상태 조회 | `quote_kr_get_market_status` | SZQM0771 |
| 기업개요 조회 | `quote_kr_get_company_overview` | IVM10050 |
| 통합차트(일/분봉 등) 조회 | `quote_kr_get_chart` | IVS11560 |

#### 시세분석

| 설명 | Tool 이름 | KB증권 API |
|---|---|---|
| ATS통합 거래대금 상위 | `ranking_kr_get_top_trading_value` | IVU10210 |
| 전일대비 등락률 상위 | `ranking_kr_get_top_change_rate` | IVU10240 |
| 가격 급등/급락 종목 | `ranking_kr_get_top_price_surge_drop` | IVU10270 |
| 당일 거래량 상위 | `ranking_kr_get_top_volume` | IVU10280 |
| 신고가/신저가 | `ranking_kr_get_new_high_low` | IVU10550 |
| 시가대비 등락률 상위 | `ranking_kr_get_top_open_price_change` | IVS10910 |
| 시가총액 상위 | `ranking_kr_get_top_market_cap` | IVS10920 |
| 시간외단일가 등락률 순위 | `ranking_kr_get_top_after_hours_change` | IVS11190 |
| 외국인/기관 매매 상위 | `ranking_kr_get_top_foreign_institution_trading` | IVU10020 |

#### 주식주문

| 설명 | Tool 이름 | KB증권 API |
|---|---|---|
| 예약주문 접수(현금/신용 통합) | `order_kr_place_reserve_order` | SSAM0831 |
| 현금 매도 주문 접수 | `order_kr_place_sell_order` | SSAM1801 |
| 현금 매수 주문 접수 | `order_kr_place_buy_order` | SSAM1802 |
| 미체결 주문 정정 | `order_kr_amend_order` | SSAM1805 |
| 미체결 주문 취소 | `order_kr_cancel_order` | SSAM1806 |
| 소수점 매도 주문 접수 | `order_kr_place_fractional_sell_order` | SSAM5762 |
| 소수점 매수 주문 접수 | `order_kr_place_fractional_buy_order` | SSAM5763 |
| 소수점 주문 취소 | `order_kr_cancel_fractional_order` | SSAM5764 |
| 매수 가능 금액/수량 조회 | `order_kr_get_buyable_amount` | SSQM1802 |

#### 계좌잔고

| 설명 | Tool 이름 | KB증권 API |
|---|---|---|
| 예수금 내역 조회 | `account_kr_get_deposit_details` | SSQM0004 |
| 보유주식 목록/상세 조회 | `account_kr_get_holdings` | SSQM1801 |
| 매매정산현황 조회 | `account_kr_get_settlement_status` | SSQM2121 |
| 기간별 매매손익현황 조회 | `account_kr_get_trading_profit_loss` | SSQM2392 |
| 일자별 실현손익 조회 | `account_kr_get_realized_profit_loss` | SSQM2442 |
| 잔고현황(결제기준) 조회 | `account_kr_get_balance_settlement_basis` | SSQM2932 |
| 잔고현황(체결기준)/총자산평가 조회 | `account_kr_get_balance_trade_basis` | SSQM2952 |
| 계좌 거래내역(입출금/매매/배당) 조회 | `account_kr_get_transaction_history` | SWQA2301 |
| 거래내역 상세 조회 | `account_kr_get_transaction_history_detail` | SWQM2412 |
| D+1/D+2 출금가능금액 조회 | `account_kr_get_withdrawable_amount` | SWQN2302 |

#### 주문내역

| 설명 | Tool 이름 | KB증권 API |
|---|---|---|
| 예약주문 처리결과 조회 | `orderhist_kr_get_reserve_order_result` | SSQM0831 |
| 예약주문 접수내역 조회 | `orderhist_kr_get_reserve_order_list` | SSQM0834 |
| 주문 체결/미체결 내역 조회 | `orderhist_kr_get_order_execution_status` | SSQM2341 |
| 소수점 매매 전체 내역 조회 | `orderhist_kr_get_fractional_trade_history` | SSQM5765 |

#### 투자정보

| 설명 | Tool 이름 | KB증권 API |
|---|---|---|
| 증시주변자금동향 조회 | `market_kr_get_market_liquidity_trend` | IVA10370 |
| 세계지수 조회 | `market_kr_get_world_indices` | IVA60140 |
| 환율종합 조회 | `market_kr_get_exchange_rates` | IVA60190 |
| 업종랭킹(MTS) 조회 | `market_kr_get_sector_ranking` | IVM30010 |
| 시장종합 조회 | `market_kr_get_market_summary` | IVSA0070 |

### 해외 주식

#### 기본시세

| 설명 | Tool 이름 | KB증권 API |
|---|---|---|
| 해외주식 종목정보 조회 | `quote_os_get_stock_info` | SIAM4983 |
| 현재가 조회 | `quote_os_get_price` | GSS10030 |
| 호가 조회 | `quote_os_get_orderbook` | GSS10040 |
| 시간대별 체결 조회 | `quote_os_get_time_trades` | GSA10020 |
| 통합차트 조회 | `quote_os_get_chart` | GSC10060 |

#### 계좌잔고

| 설명 | Tool 이름 | KB증권 API |
|---|---|---|
| 매매정산 현황 조회 | `account_os_get_settlement_status` | SPQM2205 |
| 당일 매매손익 조회 | `account_os_get_daily_profit_loss` | SPQM2206 |
| 기간별 매매손익 조회 | `account_os_get_period_profit_loss` | SPQM2207 |
| 글로벌원마켓 통합증거금 사용현황 조회 | `account_os_get_margin` | SPQM3390 |
| 해외주식 계좌 잔고평가 조회 | `account_os_get_balance` | SPQM2226 |
| 배당/무상증자 등 권리발생내역 조회 | `account_os_get_corporate_actions` | SRQM3051 |

#### 주식주문

| 설명 | Tool 이름 | KB증권 API |
|---|---|---|
| 통화별 주문가능금액 조회 | `order_os_get_buyable_amount` | SKQM2106 |
| 통화별 주문가능 예수금 현황 조회 | `order_os_get_buyable_amount_status` | SKQM3350 |
| 매도/매수 주문 접수 | `order_os_place_order` | SKAM2101 |
| 주문 정정/취소 | `order_os_amend_cancel_order` | SKAM2102 |
| 소수점 매매 주문가능금액 조회 | `order_os_get_fractional_buyable_amount` | SPQN5472 |
| 소수점 매도/매수 주문 접수 | `order_os_place_fractional_order` | SKAM2201 |
| 소수점 주문 취소 | `order_os_cancel_fractional_order` | SKAM2202 |
| 미국주식 예약주문 접수 | `order_os_place_us_reserve_order` | SPAO2104 |
| 미국주식 예약주문 취소 | `order_os_cancel_us_reserve_order` | SPAO2106 |

#### 주문내역

| 설명 | Tool 이름 | KB증권 API |
|---|---|---|
| 주문 체결내역 조회 | `orderhist_os_get_execution_history` | SPQM2103 |
| 당일 체결/미체결 현황 조회 | `orderhist_os_get_execution_status` | SPQM2204 |
| 예약주문 조회 | `orderhist_os_get_reserve_order_list` | SPQO2105 |

#### 시세분석

| 설명 | Tool 이름 | KB증권 API |
|---|---|---|
| 해외시세분석 | `ranking_os_get_market_analysis` | GSA10600 |
| 거래량 상위 | `ranking_os_get_top_volume` | GSA10150 |
| 시가총액 상위 | `ranking_os_get_top_market_cap` | GSA10170 |
| 신고/신저 조회 | `ranking_os_get_new_high_low` | GSS10180 |

각 도구의 응답(OUTPUT) 필드는 KB증권 API가 반환한 JSON을 그대로 전달합니다 (필드가 많게는
100개 이상이라 도구 설명에는 포함하지 않았습니다). 필드별 의미는 KB증권 오픈API 공식 문서를
참고하세요.

## 라이선스

[MIT](LICENSE)
