import unittest
import json
import tempfile

import main


class MainInputParsingTests(unittest.TestCase):
    def test_parse_point_accepts_comma_separated_coordinates(self):
        self.assertEqual(main.parse_point("3,4"), (3.0, 4.0))

    def test_parse_point_accepts_space_separated_coordinates(self):
        self.assertEqual(main.parse_point("3 4"), (3.0, 4.0))

    def test_load_obstacles_from_json(self):
        obstacles = main.load_obstacles("obstacles.json")
        self.assertEqual(obstacles, [])

    def test_load_obstacles_accepts_gps_circle(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
            json.dump([{"name": "surveyed zone", "lat": 17.385, "lon": 78.4867, "radius_m": 1000}], handle)
            path = handle.name
        try:
            obstacles = main.load_obstacles(path)
        finally:
            import os
            os.unlink(path)
        self.assertEqual(len(obstacles), 1)
        self.assertAlmostEqual(obstacles[0][1], 17.385 - (1000 / 111320), places=5)

    def test_rrt_star_finds_path_around_obstacle(self):
        obstacle = [(4, -1, 2, 12)]
        path, cost = main.plan_drone_route((0, 5), (10, 5), obstacles=obstacle)
        self.assertGreater(len(path), 2)
        self.assertGreater(cost, 0)
        self.assertTrue(all(not main.point_in_obstacle(point, obstacle[0]) for point in path[1:-1]))

    def test_segment_check_does_not_miss_narrow_obstacle(self):
        obstacle = [(4.99, -0.01, 0.02, 0.02)]
        self.assertFalse(main.segment_is_clear((0, 0), (10, 0), obstacle))


if __name__ == "__main__":
    unittest.main()
