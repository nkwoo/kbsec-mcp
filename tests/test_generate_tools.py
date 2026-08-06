import ast
import re

from scripts.generate_tools import (
    TOOLS_DIR,
    _build_signature,
    _name_based_description,
    _param_decl,
    load_metadata,
    render_function,
)


def test_param_decl_required_string():
    inp = {"field": "shrt_cd", "kor": "단축코드", "length": "String(6)", "required": "Y", "note": ""}
    assert _param_decl(inp) == "shrt_cd: str"


def test_param_decl_optional_string_defaults_to_none():
    inp = {"field": "nxt_key", "kor": "다음키", "length": "String(12)", "required": "N", "note": ""}
    assert _param_decl(inp) == "nxt_key: str | None = None"


def test_param_decl_object_array_is_always_optional_list():
    inp = {"field": "Record1", "kor": "Record1", "length": "Object array(10)", "required": "N", "note": ""}
    assert _param_decl(inp) == "Record1: list[dict] | None = None"


def test_build_signature_orders_required_before_optional():
    inputs = [
        {"field": "b", "kor": "B", "length": "String(1)", "required": "N", "note": ""},
        {"field": "a", "kor": "A", "length": "String(1)", "required": "Y", "note": ""},
    ]
    assert _build_signature(inputs) == "a: str, b: str | None = None"


def test_render_function_zero_input_api():
    api = {"code": "SZQM0771", "path": "/api/v1/szqm0771", "desc": "", "inputs": []}
    src = render_function("quote_kr_get_market_status", api)
    assert "async def quote_kr_get_market_status() -> dict:" in src
    assert "body: dict = {}" in src
    assert 'return await call("/api/v1/szqm0771", body)' in src
    compile(src, "<test>", "exec")


def test_render_function_with_inputs_compiles_and_builds_body():
    api = {
        "code": "IVU10140",
        "path": "/api/v1/ivu10140",
        "desc": "조회 시점의 주식 현재가를 조회 하는 API",
        "inputs": [
            {"field": "excg_clsf", "kor": "거래소구분", "length": "String(1)", "required": "Y", "note": "0:통합, 1:KRX, 2:NXT"},
            {"field": "shrt_cd", "kor": "단축코드", "length": "String(6)", "required": "Y", "note": ""},
        ],
    }
    src = render_function("quote_kr_get_price", api)
    assert "async def quote_kr_get_price(excg_clsf: str, shrt_cd: str) -> dict:" in src
    compile(src, "<test>", "exec")


def test_generated_files_define_exactly_their_metadata_functions():
    metadata = load_metadata()
    for file_stem, entries in metadata.items():
        source = (TOOLS_DIR / f"{file_stem}.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        defined = {node.name for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)}
        expected = {entry["tool_name"] for entry in entries}
        assert defined == expected


def test_name_based_description_strips_code_prefix():
    api = {"code": "SSAM1806", "name": "SSAM1806_취소주문"}
    assert _name_based_description(api) == "취소주문"


def test_name_based_description_handles_missing_name():
    api = {"code": "SSAM1806", "name": ""}
    assert _name_based_description(api) == ""


def test_no_generated_docstring_uses_bare_code_fallback():
    """Regression test: an empty excel desc must fall back to the sheet-name
    based description, never the useless "{CODE} API 호출" placeholder.
    """
    bare_fallback_pattern = re.compile(r'"""[A-Z]+\d+ API 호출')
    for path in sorted(TOOLS_DIR.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        assert not bare_fallback_pattern.search(source), (
            f"{path} contains a bare '{{CODE}} API 호출' placeholder docstring"
        )


def test_render_function_marks_trading_required_tool():
    api = {"code": "SSAM1801", "path": "/api/v1/ssam1801", "desc": "매도 주문", "inputs": []}
    src = render_function("order_kr_place_sell_order", api, requires_trading=True)
    assert 'return await call("/api/v1/ssam1801", body, requires_trading=True)' in src
    assert "⚠️" in src
    assert "KBSEC_ENABLE_TRADING" in src
    compile(src, "<test>", "exec")


def test_render_function_without_trading_omits_kwarg():
    api = {"code": "IVU10140", "path": "/api/v1/ivu10140", "desc": "현재가", "inputs": []}
    src = render_function("quote_kr_get_price", api, requires_trading=False)
    assert 'return await call("/api/v1/ivu10140", body)' in src
    assert "requires_trading" not in src
    compile(src, "<test>", "exec")


def test_generated_trading_tools_pass_requires_trading_and_match_metadata():
    """Regression test: exactly the 14 metadata-flagged trade-execution tools
    must call client.call(..., requires_trading=True); no more, no fewer.
    """
    metadata = load_metadata()
    expected_trading_names = {
        entry["tool_name"] for entries in metadata.values() for entry in entries if entry.get("trading")
    }
    assert len(expected_trading_names) == 14

    found_trading_names = set()
    for file_stem in metadata:
        source = (TOOLS_DIR / f"{file_stem}.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            has_flag = any(
                isinstance(n, ast.Call) and any(kw.arg == "requires_trading" for kw in n.keywords)
                for n in ast.walk(node)
            )
            if has_flag:
                found_trading_names.add(node.name)

    assert found_trading_names == expected_trading_names
