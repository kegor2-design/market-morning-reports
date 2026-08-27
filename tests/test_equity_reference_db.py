import io
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_korea_equity_reference_db import parse_corp_code_zip


class EquityReferenceDbTest(unittest.TestCase):
    def test_parse_corp_code_zip_keeps_listed_companies(self):
        xml = b"<result><list><corp_code>00126380</corp_code><corp_name>Samsung</corp_name><stock_code>005930</stock_code><modify_date>20260101</modify_date></list><list><corp_code>1</corp_code><corp_name>Private</corp_name><stock_code> </stock_code></list></result>"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("CORPCODE.xml", xml)
        result = parse_corp_code_zip(buffer.getvalue())
        self.assertEqual(set(result), {"005930"})
        self.assertEqual(result["005930"]["corp_code"], "00126380")


if __name__ == "__main__":
    unittest.main()
