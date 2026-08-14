"""KB증권 access token 폐기 도구.

토큰 발급(`/oauth2/token`)은 client.py가 내부적으로 자동 처리하므로 별도 도구가
필요 없다. 반면 폐기(`/oauth2/revoke`)는 KB증권이 토큰 값과 함께 발급 당시의
IP/MAC 주소를 검증해, 네트워크 환경이 바뀌면 만료 전이라도 모든 API 호출이
검증 실패로 거부될 수 있는 상황을 사용자가 직접 해소할 수 있도록 도구로 노출한다.
"""
from app import mcp
from client import revoke_token


@mcp.tool()
async def auth_revoke_token() -> dict:
    """캐시된 KB증권 access token을 폐기하고 다음 API 호출에서 즉시 재발급을 강제한다.

    KB증권 API는 토큰 값과 함께 발급 당시의 IP/MAC 주소를 함께 검증하므로, 네트워크
    환경이 바뀌어(VPN 연결, Wi-Fi 전환 등) 로컬에 캐시된 토큰의 IP/MAC이 더 이상
    일치하지 않으면 만료 전이라도 모든 API 호출이 검증 실패로 거부될 수 있다. 이
    도구를 호출하면 캐시된 토큰을 폐기하고, 다음 API 호출 시 현재 IP/MAC 기준으로
    새 토큰을 발급받는다.
    """
    revoked = await revoke_token()
    return {"revoked": revoked}
