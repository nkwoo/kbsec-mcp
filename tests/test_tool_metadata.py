import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
METADATA_PATH = ROOT / "spec" / "tool_metadata.yaml"
SPEC_PATH = ROOT / "spec" / "kbsec_api_spec.json"


def _load_metadata() -> dict:
    return yaml.safe_load(METADATA_PATH.read_text(encoding="utf-8"))


def test_metadata_covers_all_73_parsed_apis():
    apis = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    parsed_codes = {a["code"] for a in apis}
    metadata = _load_metadata()
    metadata_codes = {entry["code"] for entries in metadata.values() for entry in entries}
    assert metadata_codes == parsed_codes


def test_metadata_tool_names_are_unique():
    metadata = _load_metadata()
    names = [entry["tool_name"] for entries in metadata.values() for entry in entries]
    assert len(names) == 73
    assert len(set(names)) == 73


def test_metadata_tool_names_match_file_prefix():
    prefixes = {
        "domestic_quote": "quote_kr_",
        "domestic_ranking": "ranking_kr_",
        "domestic_order": "order_kr_",
        "domestic_account": "account_kr_",
        "domestic_order_history": "orderhist_kr_",
        "domestic_market": "market_kr_",
        "overseas_quote": "quote_os_",
        "overseas_account": "account_os_",
        "overseas_order": "order_os_",
        "overseas_order_history": "orderhist_os_",
        "overseas_ranking": "ranking_os_",
    }
    metadata = _load_metadata()
    assert set(metadata.keys()) == set(prefixes.keys())
    for file_stem, entries in metadata.items():
        for entry in entries:
            assert entry["tool_name"].startswith(prefixes[file_stem])
