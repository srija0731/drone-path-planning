import unittest

import main


class MainInputParsingTests(unittest.TestCase):
    def test_parse_point_accepts_comma_separated_coordinates(self):
        self.assertEqual(main.parse_point("3,4"), (3.0, 4.0))

    def test_parse_point_accepts_space_separated_coordinates(self):
        self.assertEqual(main.parse_point("3 4"), (3.0, 4.0))

    def test_load_obstacles_from_json(self):
        obstacles = main.load_obstacles("obstacles.json")
        self.assertTrue(len(obstacles) >= 1)
        self.assertEqual(obstacles[0][0], 6)

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
