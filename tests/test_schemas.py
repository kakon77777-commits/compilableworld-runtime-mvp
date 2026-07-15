from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from compilableworld.compiler import CompileError, compile_world
from compilableworld.schema_registry import SCHEMA_CATALOG_FORMAT, schema_catalog, schema_contracts
from compilableworld.studio import package_overview


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "mingyun_zhiyu_peace_city"


class SchemaContractTests(unittest.TestCase):
    def test_checked_in_contracts_are_versioned_and_discoverable(self) -> None:
        contracts = schema_contracts(verify=True)
        catalog = schema_catalog()

        self.assertEqual(catalog["format"], SCHEMA_CATALOG_FORMAT)
        self.assertTrue(catalog["read_only"])
        self.assertEqual(
            set(contracts),
            {"functions", "scenarios", "runtime_package", "rooms", "exits", "entities", "items", "studio_world_ir", "studio_mapping"},
        )
        for record in catalog["schemas"]:
            document = json.loads((ROOT / "schemas" / record["filename"]).read_text(encoding="utf-8"))
            self.assertEqual(document["$id"], contracts[record["key"]])
            self.assertEqual(document["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertTrue(record["available"])

    def test_compiled_package_and_studio_overview_expose_contract_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package_path = compile_world(EXAMPLE, temp)
            package = json.loads(package_path.read_text(encoding="utf-8"))
            overview = package_overview(package)

        self.assertEqual(package["schema_contracts"], schema_contracts())
        self.assertEqual(overview["schema_contracts"], schema_contracts())
        self.assertEqual(
            package["manifest"]["source_schemas"],
            {key: schema_contracts()[key] for key in ("rooms", "exits", "entities", "items", "functions", "scenarios")},
        )

    def test_csv_header_contract_rejects_unknown_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "world"
            shutil.copytree(EXAMPLE, source)
            rooms_path = source / "data" / "rooms.csv"
            lines = rooms_path.read_text(encoding="utf-8").splitlines()
            lines[0] += ",unknown_column"
            rooms_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(CompileError, "CSV Schema"):
                compile_world(source, Path(temp) / "build")


if __name__ == "__main__":
    unittest.main()
