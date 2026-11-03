#!/usr/bin/env python3
"""
TDD Unit Test: Cereal custom.capnp schema validation
Seam: cereal/custom.capnp file & schema fields
Verifies:
1. File exists and contains valid Cap'n Proto syntax for AmapNavi.
2. Field @15 is overtakeMode :Int32.
3. Field @16 is lidarBehindVdistTime :Float32.
4. Schema struct AmapNavi has ID @0xaedffd8f31e7b55d.
"""
import os
import re
import unittest

C3_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))

class TestCerealCustomSchema(unittest.TestCase):

    def setUp(self):
        self.capnp_file = os.path.join(C3_ROOT, "cereal", "custom.capnp")
        self.assertTrue(os.path.exists(self.capnp_file), f"custom.capnp missing at {self.capnp_file}")
        with open(self.capnp_file, "r", encoding="utf-8") as f:
            self.content = f.read()

    def test_amap_navi_struct_id(self):
        """Verify struct AmapNavi exists with exact Cap'n Proto 64-bit ID"""
        self.assertIn("struct AmapNavi @0xaedffd8f31e7b55d", self.content,
                      "struct AmapNavi MUST retain its canonical Cap'n Proto ID!")

    def test_overtake_mode_field(self):
        """Verify overtakeMode is defined at field offset @15 as Int32"""
        match = re.search(r"overtakeMode\s*@15\s*:\s*Int32\s*;", self.content)
        self.assertIsNotNone(match, "overtakeMode field MUST be defined as '@15 : Int32;' in struct AmapNavi")

    def test_lidar_behind_vdist_time_field(self):
        """Verify lidarBehindVdistTime is defined at field offset @16 as Float32"""
        match = re.search(r"lidarBehindVdistTime\s*@16\s*:\s*Float32\s*;", self.content)
        self.assertIsNotNone(match, "lidarBehindVdistTime field MUST be defined as '@16 : Float32;' in struct AmapNavi")

    def test_field_numbering_sequential(self):
        """Verify field numbers 0 through 16 are contiguous without gaps or duplicates"""
        amap_block = re.search(r"struct AmapNavi @0xaedffd8f31e7b55d\s*\{([^}]+)\}", self.content)
        self.assertIsNotNone(amap_block, "Could not extract struct AmapNavi block")
        body = amap_block.group(1)
        offsets = [int(m) for m in re.findall(r"@(\d+)", body)]
        self.assertEqual(offsets, list(range(17)), f"Offsets in AmapNavi must be contiguous 0..16, got {offsets}")

if __name__ == "__main__":
    unittest.main()
