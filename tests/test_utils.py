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
from src.algorithms.common import CachedEvaluator, make_cache_key, quantize_vector, random_grid_population


class DummyLogger:
    def __init__(self):
        self.trials = []

    def write_trial(self, vector, score, individual_powers):
        self.trials.append((vector.copy(), score, list(individual_powers)))

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


class TestGridQuantization(unittest.TestCase):
    def setUp(self):
        self.config = {
            'bounds': [[0.5, 3.0], [2.5, 4.0]],
            'step_size': 0.25,
        }

    def test_quantize_vector_uses_config_step_size(self):
        vector = np.array([0.62, 3.88])
        quantized = quantize_vector(vector, self.config)
        expected = np.array([0.5, 4.0])
        np.testing.assert_array_almost_equal(quantized, expected)

    def test_cache_key_uses_grid_indices(self):
        v1 = quantize_vector(np.array([0.62, 3.88]), self.config)
        v2 = quantize_vector(np.array([0.51, 3.99]), self.config)
        self.assertEqual(make_cache_key(v1, self.config), make_cache_key(v2, self.config))

    def test_random_grid_population_is_on_step_grid(self):
        np.random.seed(1)
        population = random_grid_population(20, self.config)
        lower_bounds = np.array(self.config['bounds'][0])
        step_indices = (population - lower_bounds) / self.config['step_size']
        np.testing.assert_array_almost_equal(step_indices, np.round(step_indices))


class TestCachedEvaluator(unittest.TestCase):
    def test_cache_hit_skips_duplicate_physics_evaluation(self):
        config = {
            'bounds': [[0.5, 3.0], [2.5, 4.0]],
            'step_size': 0.25,
            'opt_mode': 1,
            'num_wecs': 1,
        }
        logger = DummyLogger()
        calls = []

        def eval_func(vector, _config):
            calls.append(vector.copy())
            return float(np.sum(vector)), [float(vector[0])]

        evaluator = CachedEvaluator(config, eval_func, logger)
        first = evaluator.evaluate(np.array([0.62, 3.88]))
        second = evaluator.evaluate(np.array([0.51, 3.99]))

        self.assertEqual(first, second)
        self.assertEqual(len(calls), 1)
        self.assertEqual(evaluator.total_evals, 1)
        self.assertEqual(evaluator.cache_hits, 1)
        self.assertEqual(len(logger.trials), 1)

    def test_canonicalized_5_wec_layout_hits_same_cache_entry(self):
        config = {
            'bounds': [[3.0, 3.0, 0.0, 3.0, 0.0], [25.0, 25.0, 30.0, 25.0, 30.0]],
            'step_size': 0.1,
            'opt_mode': 2,
            'num_wecs': 5,
        }
        logger = DummyLogger()
        calls = []

        def eval_func(vector, _config):
            calls.append(vector.copy())
            return 123.0, [1.0] * 5

        evaluator = CachedEvaluator(config, eval_func, logger)
        evaluator.evaluate(np.array([10.0, 25.0, 30.0, 15.0, 20.0]))
        evaluator.evaluate(np.array([10.0, 15.0, 20.0, 25.0, 30.0]))

        self.assertEqual(len(calls), 1)
        self.assertEqual(evaluator.total_evals, 1)
        self.assertEqual(evaluator.cache_hits, 1)
        np.testing.assert_array_almost_equal(calls[0], np.array([10.0, 15.0, 20.0, 25.0, 30.0]))

if __name__ == '__main__':
    unittest.main()
