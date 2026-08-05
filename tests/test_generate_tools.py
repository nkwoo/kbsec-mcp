import ast

from scripts.generate_tools import (
    TOOLS_DIR,
    _build_signature,
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
