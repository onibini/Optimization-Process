import unittest
import os
import tempfile
import numpy as np

# Add project root to sys.path if not present
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.mapper import decode_symmetric_positions, canonicalize_vector_inplace
from src.utils.geometry import check_min_distance
from src.utils.data_handler import load_env_data

class TestMapper(unittest.TestCase):
    def test_decode_symmetric_positions_3_wecs(self):
        # 3 WECs layout vector: [x1, x2, y2]
        vector = [10.0, 20.0, 15.0]
        positions = decode_symmetric_positions(vector, num_wecs=3)
        expected = [(10.0, 0.0), (20.0, 15.0), (20.0, -15.0)]
        self.assertEqual(positions, expected)

    def test_decode_symmetric_positions_5_wecs(self):
        # 5 WECs layout vector: [x1, x2, y2, x3, y3]
        # x2, y2 and x3, y3 will be sorted inside decode_symmetric_positions
        vector = [10.0, 30.0, 40.0, 20.0, 25.0]
        positions = decode_symmetric_positions(vector, num_wecs=5)
        # s_x2, s_y2 should be sorted from [(30, 40), (20, 25)] -> (20, 25) comes first
        expected = [
            (10.0, 0.0),
            (20.0, 25.0), (20.0, -25.0), # WEC 2 & symmetric partner
            (30.0, 40.0), (30.0, -40.0)  # WEC 3 & symmetric partner
        ]
        self.assertEqual(positions, expected)

    def test_canonicalize_layout_vector(self):
        # Layout mode (opt_mode=2), 5 WECs: [x1, x2, y2, x3, y3]
        v_unsorted = np.array([10.0, 25.0, 30.0, 15.0, 20.0])
        canonicalize_vector_inplace(v_unsorted, opt_mode=2, num_wecs=5)
        expected = np.array([10.0, 15.0, 20.0, 25.0, 30.0])
        np.testing.assert_array_almost_equal(v_unsorted, expected)

    def test_canonicalize_joint_vector(self):
        # Joint mode (opt_mode=3), 5 WECs: [radius, draft, x1, x2, y2, x3, y3]
        v_unsorted = np.array([2.5, 5.0, 10.0, 25.0, 30.0, 15.0, 20.0])
        canonicalize_vector_inplace(v_unsorted, opt_mode=3, num_wecs=5)
        expected = np.array([2.5, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0])
        np.testing.assert_array_almost_equal(v_unsorted, expected)


class TestGeometry(unittest.TestCase):
    def test_check_min_distance_no_violation(self):
        # WEC radius = 2.5, min_spacing = 4.0 -> min allowed distance = 10.0
        positions = [(10.0, 0.0), (25.0, 0.0)]
        violation = check_min_distance(positions, radius=2.5, min_spacing=4.0)
        self.assertEqual(violation, 0.0)

    def test_check_min_distance_with_violation(self):
        # WEC radius = 2.5, min_spacing = 4.0 -> min allowed distance = 10.0
        positions = [(10.0, 0.0), (15.0, 0.0)] # distance = 5.0
        violation = check_min_distance(positions, radius=2.5, min_spacing=4.0)
        # violation = 10.0 - 5.0 = 5.0
        self.assertAlmostEqual(violation, 5.0)


class TestDataHandler(unittest.TestCase):
    def setUp(self):
        # Create a temporary CSV file
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_csv = os.path.join(self.temp_dir.name, 'test_env_data.csv')
        with open(self.temp_csv, 'w', encoding='utf-8') as f:
            f.write("SiteID,SiteName,Hs,Tp,Gamma,Depth\n")
            f.write("1,TestSite,1.5,6.0,1.4,45.0\n")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_load_env_data_success(self):
        data = load_env_data(site_id=1, filepath=self.temp_csv)
        self.assertEqual(data['SiteName'], 'TestSite')
        self.assertEqual(data['Hs'], 1.5)
        self.assertEqual(data['Tp'], 6.0)
        self.assertEqual(data['Gamma'], 1.4)
        self.assertEqual(data['Depth'], 45.0)

    def test_load_env_data_invalid_id(self):
        with self.assertRaises(ValueError):
            load_env_data(site_id=999, filepath=self.temp_csv)

if __name__ == '__main__':
    unittest.main()
