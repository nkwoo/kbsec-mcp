"""KB증권 MCP 서버 인스턴스.

tools/*.py와 server.py가 공유하는 단일 MCPServer 인스턴스. 순환 import를 피하기 위해
별도 모듈로 분리한다.
"""
from mcp.server import MCPServer

mcp = MCPServer("kbsec")
