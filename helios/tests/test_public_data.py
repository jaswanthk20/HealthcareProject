"""Regression tests against the actual publisher download, not a generated dataset."""
import csv
import io
import json
from pathlib import Path
import sys
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from helios import public_data as data
from helios.agent import ask


class PublicDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw, cls.metadata = data.download(ROOT / "data/official", offline=True)
        cls.payload = data.build_payload(cls.raw, cls.metadata)

    def test_source_provenance_and_coverage(self):
        p = self.payload
        self.assertEqual(p["source"]["publisher"], "Statistics Canada")
        self.assertEqual(p["source"]["table"], "13-10-0905-01")
        self.assertEqual(len(p["source"]["source_sha256"]), 64)
        self.assertEqual(set(p["indicators"]), set(data.INDICATORS))
        self.assertGreater(len(p["rows"]), 1000)
        self.assertTrue(all(int(r["year"]) >= 2022 for r in p["rows"]))

    def test_every_exported_value_matches_its_publisher_vector(self):
        with zipfile.ZipFile(io.BytesIO(self.raw)) as z:
            with z.open("13100905.csv") as source:
                reader = csv.DictReader(io.TextIOWrapper(source, encoding="utf-8-sig"))
                official = {(r["REF_DATE"], r["VECTOR"]): r for r in reader
                            if r["Characteristics"] in ("Percent", "Low 95% confidence interval, percent",
                                                        "High 95% confidence interval, percent")}
        for row in self.payload["rows"]:
            for field in ("value", "low", "high"):
                origin = official[(row["year"], row[field + "_vector"])]
                self.assertEqual(row[field + "_status"], origin["STATUS"])
                expected = data.number(origin)
                if field != "value" and row["value"] is None:
                    expected = None
                self.assertEqual(row[field], expected)

    def test_suppressed_cells_never_expose_values_or_bounds(self):
        suppressed = [r for r in self.payload["rows"] if r["value_status"] in ("F", "x", "..", "...")]
        self.assertTrue(suppressed)
        for row in suppressed:
            self.assertIsNone(row["value"])
            self.assertIsNone(row["low"])
            self.assertIsNone(row["high"])
            self.assertEqual(row["quality"], "unavailable")

    def test_caution_flags_are_preserved(self):
        caution = [r for r in self.payload["rows"] if r["value_status"] == "E" and r["value"] is not None]
        self.assertTrue(caution)
        self.assertTrue(all(r["quality"] == "caution" for r in caution))

    def test_unexpected_values_fail_closed(self):
        for value, status in [("101", ""), ("nan", ""), ("-1", ""), ("2", "new-flag")]:
            with self.subTest(value=value, status=status), self.assertRaises(ValueError):
                data.number({"VALUE": value, "STATUS": status})
        self.assertIsNone(data.number({"VALUE": "", "STATUS": ""}))
        self.assertEqual(data.number({"VALUE": "0", "STATUS": ""}), 0)

    def test_missing_source_schema_is_rejected(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("13100905.csv", "wrong,column\n1,2\n")
        with self.assertRaisesRegex(ValueError, "schema changed"):
            data.parse_archive(buf.getvalue())

    def test_duplicate_source_rows_are_rejected(self):
        with zipfile.ZipFile(io.BytesIO(self.raw)) as z:
            contents = z.read("13100905.csv").decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(contents))
        row = next(r for r in reader if r["REF_DATE"] == "2022" and r["Indicators"] == "Diabetes"
                   and r["Characteristics"] == "Percent")
        text = io.StringIO()
        writer = csv.DictWriter(text, fieldnames=reader.fieldnames)
        writer.writeheader()
        writer.writerows([row, row])
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("13100905.csv", text.getvalue())
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            data.parse_archive(buf.getvalue())

    def test_exact_population_answer_quotes_source_cell(self):
        year = self.payload["source"]["latest_year"]
        answer = ask(self.payload, f"What percentage has diabetes in Ontario in {year}?")
        self.assertEqual(answer["status"], "answered")
        self.assertEqual(len(answer["rows"]), 1)
        row = answer["rows"][0]
        self.assertEqual(row["geography"], "Ontario")
        self.assertEqual(row["year"], year)
        self.assertIn(str(row["value"]), answer["text"])
        self.assertIn(self.payload["source"]["url"], answer["text"])

    def test_unsupported_and_individual_questions_are_refused(self):
        for question in ["Who is the patient with diabetes?", "Diabetes by rurality",
                         "Diabetes drug brand share", "Predict the individual patient outcome",
                         "What is the weather?", "Diabetes and anxiety rates"]:
            with self.subTest(question=question):
                self.assertEqual(ask(self.payload, question)["status"], "refused")

    def test_unknown_year_is_not_silently_replaced(self):
        self.assertEqual(ask(self.payload, "Diabetes in 2099")["status"], "unavailable")

    def test_rebuild_is_stable_except_retrieval_timestamp(self):
        old = json.loads((ROOT / "outputs/dashboard_data.json").read_text(encoding="utf-8"))
        new = self.payload
        new["source"]["retrieved_at"] = old["source"]["retrieved_at"]
        self.assertEqual(old, new)


if __name__ == "__main__":
    unittest.main()
