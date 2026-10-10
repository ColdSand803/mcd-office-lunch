import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcd_office_lunch.mcp_client import parse_message, unwrap_tool

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_SHA = "136e76f3160317049f19f5ba03f4d0fedd70fc3c"


class ClientParseTests(unittest.TestCase):
    def test_sse_payload(self) -> None:
        raw = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n'
        self.assertEqual(parse_message(raw)["result"]["ok"], True)

    def test_tool_text_is_json(self) -> None:
        result = unwrap_tool({"content": [{"type": "text", "text": "{\"storeCode\":\"1\"}"}]})
        self.assertEqual(result["storeCode"], "1")

    def test_declaration_bytes_match_official_template(self) -> None:
        blob = (ROOT / "CONTEST_DECLARATION.md").read_bytes()
        digest = hashlib.sha1(b"blob %d\0" % len(blob) + blob).hexdigest()
        self.assertEqual(digest, OFFICIAL_SHA)


if __name__ == "__main__":
    unittest.main()
