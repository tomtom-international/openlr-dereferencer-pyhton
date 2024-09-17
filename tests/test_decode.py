"Contains the unit tests for the decoding logic"
import unittest
from math import degrees
from itertools import zip_longest
from io import StringIO
from typing import List, Iterable, TypeVar, NamedTuple
from shapely.geometry import LineString
from openlr import Coordinates, FRC, FOW, LineLocationReference, LocationReferencePoint,\
    PointAlongLineLocationReference, Orientation, SideOfRoad, PoiWithAccessPointLocationReference, \
    GeoCoordinateLocationReference

from openlr_dereferencer import decode, Config
from openlr_dereferencer.decoding import PointAlongLine, LineLocation, LRDecodeError, PoiWithAccessPoint
from openlr_dereferencer.decoding.candidate_functions import nominate_candidates, make_candidate
from openlr_dereferencer.decoding.scoring import score_geolocation, score_frc, \
    score_bearing, score_angle_difference
from openlr_dereferencer.decoding.routes import PointOnLine, Route
from openlr_dereferencer.decoding.path_math import remove_offsets
from openlr_dereferencer.observer import SimpleObserver
from openlr_dereferencer.example_sqlite_map import ExampleMapReader
from openlr_dereferencer.maps.wgs84 import distance, bearing, extrapolate

from .example_mapformat import setup_testdb, setup_testdb_in_memory, remove_db_file

from openlr_dereferencer import load_config, save_config, DEFAULT_CONFIG

class DummyNode():
    "Fake Node class for unit testing"
    def __init__(self, coord: Coordinates):
        self.coord = coord

    def __str__(self) -> str:
        return f"Node at {self.coord}"

    @property
    def coordinates(self) -> Coordinates:
        "Return the saved coordinates"
        return self.coord

class DummyLine(NamedTuple):
    "Fake Line class for unit testing"
    line_id: int
    start_node: DummyNode
    end_node: DummyNode

    def __str__(self) -> str:
        return (
            f"Line with id {self.line_id} and length {self.length} "
            f"from {self.start_node.coord} to {self.end_node.coord}"
        )

    def coordinates(self) -> List[Coordinates]:
        "Returns a list of this line's coordinates"
        return [self.start_node.coord, self.end_node.coord]

    @property
    def length(self) -> float:
        "Return distance between star and end node"
        return distance(self.start_node.coord, self.end_node.coord)

    @property
    def geometry(self) -> LineString:
        return LineString([(c.lon, c.lat) for c in self.coordinates()])

def get_test_linelocation_1():
    "Return a prepared line location with 3 LRPs"
    # References node 0 / line 1 / lines 1, 3
    lrp1 = LocationReferencePoint(13.41, 52.525,
                                  FRC.FRC0, FOW.SINGLE_CARRIAGEWAY, 90.0,
                                  FRC.FRC2, 717.8)
    # References node 3 / line 4
    lrp2 = LocationReferencePoint(13.4145, 52.529,
                                  FRC.FRC2, FOW.SINGLE_CARRIAGEWAY, 170,
                                  FRC.FRC2, 456.6)
    # References node 4 / line 4
    lrp3 = LocationReferencePoint(13.416, 52.525, FRC.FRC2,
                                  FOW.SINGLE_CARRIAGEWAY, 320.0, None, None)
    return LineLocationReference([lrp1, lrp2, lrp3], 0.0, 0.0)


def get_test_linelocation_2():
    "Return a undecodable line location with 2 LRPs"
    # References node 0 / line 1 / lines 1, 3
    lrp1 = LocationReferencePoint(13.41, 52.525,
                                  FRC.FRC0, FOW.SINGLE_CARRIAGEWAY, 90.0,
                                  FRC.FRC2, 0.0)
    # References node 13 / ~ line 17
    lrp2 = LocationReferencePoint(13.429, 52.523, FRC.FRC2,
                                  FOW.SINGLE_CARRIAGEWAY, 270.0, None, None)
    return LineLocationReference([lrp1, lrp2], 0.0, 0.0)


def get_test_linelocation_3():
    """Returns a line location that is within a line.
    
    This simulates that the start and end junction are missing on the target map."""
    # References a point on line 1
    lrp1 = LocationReferencePoint(13.411, 52.525,
                                  FRC.FRC1, FOW.SINGLE_CARRIAGEWAY, 90.0,
                                  FRC.FRC1, 135)
    # References another point on line 1
    lrp2 = LocationReferencePoint(13.413, 52.525, FRC.FRC1,
                                  FOW.SINGLE_CARRIAGEWAY, -90.0, None, None)
    return LineLocationReference([lrp1, lrp2], 0.0, 0.0)

def get_test_linelocation_4() -> LineLocationReference:
    "Test backtracking with a location that tries the decoder to get lost"
    # Seems to reference line 19 -> Decoder gets lost
    lrp1 = LocationReferencePoint(13.41, 52.5245, FRC.FRC2, FOW.SINGLE_CARRIAGEWAY, 120.0, FRC.FRC2, 424)
    # Matches still roughly line 19
    lrp2 = LocationReferencePoint(13.4125, 52.521, FRC.FRC2, FOW.SINGLE_CARRIAGEWAY, 130.0, FRC.FRC2, 1313)
    # Matches only line 20 -> Decoding fails and backtracking resolves LRPs 1 and 2 to line 20
    lrp3 = LocationReferencePoint(13.429, 52.523, FRC.FRC2, FOW.SINGLE_CARRIAGEWAY, 230.0, None, None)
    return LineLocationReference([lrp1, lrp2, lrp3], 0.0, 0.0)


def get_test_pointalongline() -> PointAlongLineLocationReference:
    "Get a test Point Along Line location reference"
    path_ref = get_test_linelocation_1().points[-2:]
    return PointAlongLineLocationReference(path_ref, 0.5, Orientation.WITH_LINE_DIRECTION, \
                                  SideOfRoad.RIGHT)


def get_test_invalid_pointalongline() -> PointAlongLineLocationReference:
    "Get a test Point Along Line location reference"
    path_ref = get_test_linelocation_1().points[-2:]
    return PointAlongLineLocationReference(path_ref, 1500, Orientation.WITH_LINE_DIRECTION, \
                                  SideOfRoad.RIGHT)


def get_test_poi() -> PoiWithAccessPointLocationReference:
    "Get a test POI with access point location reference"
    path_ref = get_test_linelocation_1().points[-2:]
    return PoiWithAccessPointLocationReference(
        path_ref, 0.5, 13.414, 52.526, Orientation.WITH_LINE_DIRECTION,
        SideOfRoad.RIGHT)

T = TypeVar("T")


class DecodingTests(unittest.TestCase):
    "Unittests for the decoding logic"

    def assertIterableAlmostEqual(self, iter_a: Iterable[T], iter_b: Iterable[T], delta: float):
        """Tests if `a` and `b` iterate over nearly-equal floats.

        This means, that two floats of the same index in `a` and `b` should not have a greater
        difference than `delta`."""
        # Get the generators
        gen_a = iter(iter_a)
        gen_b = iter(iter_b)
        for (a, b) in zip_longest(gen_a, gen_b):
            if abs(a - b) > delta:
                list_a = [a] + list(gen_a)
                list_b = [b] + list(gen_b)
                msg = (f"Iterables are not almost equal within delta {delta}.\n"
                       f"Remaining a: {list_a}\nRemaining b: {list_b}")
                raise self.failureException(msg)

    def setUp(self):
        self.reader = ExampleMapReader(":memory:")
        self.reader.connection = setup_testdb_in_memory()
        self.config = Config()

    def test_make_candidates_with_zero_length_line(self):
        lrp = LocationReferencePoint(0.0, 0.0, None, None, None, None, None)
        node1 = DummyNode(Coordinates(0.0, 0.0))
        node2 = DummyNode(Coordinates(0.0, 0.0))
        line = DummyLine(0, node1, node2)
        self.assertEqual(make_candidate(lrp, line, self.config, None, False), None)

    def test_geoscore_1(self):
        "Test scoring an excactly matching LRP candidate line"
        lrp = LocationReferencePoint(0.0, 0.0, None, None, None, None, None)
        node1 = DummyNode(Coordinates(0.0, 0.0))
        node2 = DummyNode(Coordinates(0.0, 90.0))
        pal = PointOnLine(DummyLine(None, node1, node2), 0.0)
        score = score_geolocation(lrp, pal, 1.0)
        self.assertEqual(score, 1.0)

    def test_geoscore_0(self):
        "Test scoring a non-matching LRP candidate line"
        lrp = LocationReferencePoint(0.0, 0.0, None, None, None, None, None)
        node1 = DummyNode(Coordinates(0.0, 0.0))
        node2 = DummyNode(Coordinates(0.0, 90.0))
        pal = PointOnLine(DummyLine(None, node1, node2), 1.0)
        score = score_geolocation(lrp, pal, 1.0)
        self.assertEqual(score, 0.0)

    def test_frcscore_0(self):
        "Test scoring two non-matching FRCs"
        frc_a = FRC.FRC0
        frc_b = FRC.FRC7
        self.assertEqual(score_frc(frc_a, frc_b), 0.0)
        self.assertEqual(score_frc(frc_b, frc_a), 0.0)

    def test_frcscore_1(self):
        "Test scoring two equal FRCs"
        frc = FRC.FRC0
        # If it would not be exactly 1.0, it would be weird
        self.assertEqual(score_frc(frc, frc), 1.0)

    def test_fowscore_0(self):
        "Test scoring two non-matching FOWs"
        fow_a = FOW.UNDEFINED
        fow_b = FOW.OTHER
        self.assertAlmostEqual(self.config.fow_standin_score[fow_a][fow_b], 0.5)
        self.assertAlmostEqual(self.config.fow_standin_score[fow_b][fow_a], 0.5)

    def test_fowscore_1(self):
        "Test scoring two equal FOWs"
        fow = FOW.MOTORWAY
        self.assertEqual(self.config.fow_standin_score[fow][fow], 1.0)

    def test_bearingscore_1(self):
        "Test bearing difference of +90°"
        node1 = DummyNode(Coordinates(0.0, 0.0))
        node2 = DummyNode(Coordinates(0.0, 90.0))
        node3 = DummyNode(Coordinates(1.0, 0.0))
        wanted_bearing = degrees(bearing(node1.coordinates, node2.coordinates))
        wanted = LocationReferencePoint(13.416, 52.525, FRC.FRC2,
                                        FOW.SINGLE_CARRIAGEWAY, wanted_bearing, None, None)
        line = DummyLine(1, node1, node3)
        score = score_bearing(wanted, PointOnLine(line, 0.0), False, self.config.bear_dist)
        self.assertEqual(score, 0.5)

    def test_bearingscore_2(self):
        "Test bearing difference of -90°"
        node1 = DummyNode(Coordinates(0.0, 0.0))
        node2 = DummyNode(Coordinates(0.0, 90.0))
        node3 = DummyNode(Coordinates(-1.0, 0.0))
        wanted_bearing = degrees(bearing(node1.coordinates, node2.coordinates))
        wanted = LocationReferencePoint(13.416, 52.525, FRC.FRC2,
                                        FOW.SINGLE_CARRIAGEWAY, wanted_bearing, None, None)
        line = DummyLine(1, node1, node3)
        score = score_bearing(wanted, PointOnLine(line, 0.0), False, self.config.bear_dist)
        self.assertEqual(score, 0.5)

    def test_bearingscore_3(self):
        "Test bearing difference of +90°"
        node1 = DummyNode(Coordinates(0.0, 0.0))
        node2 = DummyNode(Coordinates(0.0, 90.0))
        node3 = DummyNode(Coordinates(1.0, 0.0))
        wanted_bearing = degrees(bearing(node1.coordinates, node2.coordinates))
        wanted = LocationReferencePoint(13.416, 52.525, FRC.FRC2,
                                        FOW.SINGLE_CARRIAGEWAY, wanted_bearing, None, None)
        line = DummyLine(1, node1, node3)
        score = score_bearing(wanted, PointOnLine(line, 1.0), True, self.config.bear_dist)
        self.assertAlmostEqual(score, 0.5)

    def test_bearingscore_4(self):
        "Test bearing difference of -90°"
        node1 = DummyNode(Coordinates(0.0, 0.0))
        node2 = DummyNode(Coordinates(0.0, 90.0))
        node3 = DummyNode(Coordinates(-1.0, 0.0))
        wanted_bearing = degrees(bearing(node1.coordinates, node2.coordinates))
        wanted = LocationReferencePoint(13.416, 52.525, FRC.FRC2,
                                        FOW.SINGLE_CARRIAGEWAY, wanted_bearing, None, None)
        line = DummyLine(1, node1, node3)
        score = score_bearing(wanted, PointOnLine(line, 1.0), True, self.config.bear_dist)
        self.assertAlmostEqual(score, 0.5)

    def test_bearingscore_5(self):
        "Test perfect/worst possible bearing"
        node1 = DummyNode(Coordinates(1.0, 0.0))
        node2 = DummyNode(Coordinates(0.0, 0.0))
        wanted_bearing = degrees(bearing(node1.coordinates, node2.coordinates))
        wanted = LocationReferencePoint(13.416, 52.525, FRC.FRC2,
                                        FOW.SINGLE_CARRIAGEWAY, wanted_bearing, None, None)
        line = DummyLine(1, node1, node2)
        score = score_bearing(wanted, PointOnLine(line, 0.0), False, self.config.bear_dist)
        self.assertAlmostEqual(score, 1.0)
        score = score_bearing(wanted, PointOnLine(line, 1.0), True, self.config.bear_dist)
        self.assertAlmostEqual(score, 0.0)

    def test_anglescore_1(self):
        "Test the angle scoring function from 0"
        sub_testcases = [-360, -720, 0, 180, 540, 720]
        scores = map(lambda arc: score_angle_difference(0, arc), sub_testcases)
        self.assertIterableAlmostEqual([1.0, 1.0, 1.0, 0.0, 0.0, 1.0], list(scores), 0.001)

    def test_anglescore_2(self):
        "Test the angle scoring function from 271°"
        sub_testcases = [-89, 91, 181, 226]
        scores = map(lambda arc: score_angle_difference(271, arc), sub_testcases)
        self.assertIterableAlmostEqual([1.0, 0.0, 0.5, 0.75], list(scores), 0.001)

    def test_generate_candidates_1(self):
        "Generate candidates and pick the best"
        reference = get_test_linelocation_1()
        candidates = list(nominate_candidates(reference.points[0], self.reader, self.config, None, False))
        # Sort by score
        candidates.sort(key=lambda candidate: candidate.score, reverse=True)
        # Get only the line ids
        candidates = [candidate.line.line_id for candidate in candidates]
        # Now assert the best
        self.assertEqual(candidates[0], 1)

    def test_decode_3_lrps(self):
        "Decode a line location of 3 LRPs"
        reference = get_test_linelocation_1()
        location = decode(reference, self.reader)
        self.assertTrue(isinstance(location, LineLocation))
        lines = [l.line_id for l in location.lines]
        self.assertListEqual([1, 3, 4], lines)
        for (a, b) in zip(location.coordinates(),
                             [Coordinates(13.41, 52.525), Coordinates(13.414, 52.525),
                              Coordinates(13.4145, 52.529), Coordinates(13.416, 52.525)]):
            self.assertAlmostEqual(a.lon, b.lon, delta=0.00001)
            self.assertAlmostEqual(a.lat, b.lat, delta=0.00001)

    def test_decode_nopath(self):
        "Decode a line location where no short-enough path exists"
        reference = get_test_linelocation_2()
        with self.assertRaises(LRDecodeError):
            decode(reference, self.reader)

    def test_inapt_reference_type(self):
        with self.assertRaises(LRDecodeError):
            decode("Hello", self.reader)

    def test_decode_offsets(self):
        "Decode a line location with offsets"
        reference = get_test_linelocation_1()
        reference = reference._replace(poffs=0.25)
        reference = reference._replace(noffs=0.75)
        path = decode(reference, self.reader)
        self.assertTrue(isinstance(path, LineLocation))
        path = path.coordinates()
        self.assertEqual(len(path), 4)
        self.assertAlmostEqual(path[0].lon, 13.4126, delta=0.001)
        self.assertAlmostEqual(path[0].lat, 52.525, delta=0.001)
        self.assertAlmostEqual(path[1].lon, 13.414, delta=0.001)
        self.assertAlmostEqual(path[1].lat, 52.525, delta=0.001)

    def test_decode_pointalongline(self):
        "Test a valid point along line location"
        # Get a list of 2 LRPs
        reference = get_test_pointalongline()
        pal: PointAlongLine = decode(reference, self.reader)
        coords = pal.coordinates()
        self.assertAlmostEqual(coords.lon, 13.4153, delta=0.0001)
        self.assertAlmostEqual(coords.lat, 52.5270, delta=0.0001)

    def test_decode_pointalong_raises(self):
        "Test an invalid point along line location with too high offset"
        # Get a list of 2 LRPs
        reference = get_test_invalid_pointalongline()
        with self.assertRaises(LRDecodeError):
            decode(reference, self.reader)

    def test_decode_poi(self):
        "Test decoding a valid POI with access point location"
        reference = get_test_poi()
        poi: PoiWithAccessPoint = decode(reference, self.reader)
        coords = poi.access_point_coordinates()
        self.assertAlmostEqual(coords.lon, 13.4153, delta=0.0001)
        self.assertAlmostEqual(coords.lat, 52.5270, delta=0.0001)
        self.assertEqual(poi.poi, Coordinates(13.414, 52.526))

    def test_decode_invalid_poi(self):
        "Test if decoding an invalid POI with access point location raises an error"
        reference = get_test_poi()
        reference = reference._replace(poffs=1500)
        with self.assertRaises(LRDecodeError):
            decode(reference, self.reader)


    def test_decode_midline(self):
        reference = get_test_linelocation_3()
        line_location = decode(reference, self.reader)
        coords = line_location.coordinates()
        self.assertEqual(len(coords), 2)
        for ((lon1, lat1), (lon2, lat2)) in zip(coords, [(13.411, 52.525), (13.413, 52.525)]):
            self.assertAlmostEqual(lon1, lon2)
            self.assertAlmostEqual(lat1, lat2)

    def test_observer_decode_3_lrps(self):
        "Add a simple observer for decoding a line location of 3 lrps "
        observer = SimpleObserver()
        reference = get_test_linelocation_1()
        decode(reference, self.reader, observer=observer)
        self.assertTrue(observer.candidates)
        self.assertListEqual([route.success for route in observer.attempted_routes], [True, True])

    def test_observer_generate_candidates_strict_bearing_threshold(self):
        "Try to generate candidates with a strict bearing threshold"
        reference = get_test_linelocation_1()
        observer = SimpleObserver()
        candidates = list(
            nominate_candidates(reference.points[0], self.reader, Config(max_bear_deviation=0), observer, False)
        )

        self.assertListEqual(candidates, [])
        self.assertDictEqual(observer.candidates, {})
        self.assertTrue(observer.failed_candidates)

    def test_observer_generate_candidates_score_threshold(self):
        "Try to generate candidates with a high min score"
        reference = get_test_linelocation_1()
        observer = SimpleObserver()
        candidates = list(
            nominate_candidates(reference.points[0], self.reader, Config(min_score=0.8), observer, False)
        )

        self.assertEqual(len(candidates), 1)
        self.assertTrue(observer.failed_candidates)

    def test_observer_decode_pointalongline(self):
        "Add a simple observer for decoding a valid point along line location"
        reference = get_test_pointalongline()
        observer = SimpleObserver()
        decode(reference, self.reader, observer=observer)
        self.assertTrue(observer.candidates)
        self.assertListEqual([route.success for route in observer.attempted_routes], [True])

    def test_observer_decode_poi(self):
        "Add a simple observer for decoding a valid POI with access point location"
        reference = get_test_poi()
        observer = SimpleObserver()
        decode(reference, self.reader, observer=observer)
        self.assertTrue(observer.candidates)
        self.assertListEqual([route.success for route in observer.attempted_routes], [True])

    def test_decode_coord(self):
        coord = Coordinates(13.0, 51.0)
        reference = GeoCoordinateLocationReference(coord)
        location = decode(reference, self.reader)
        self.assertAlmostEqual(coord.lon, location.lon)
        self.assertAlmostEqual(coord.lat, location.lat)

    def test_bearing_threshold(self):
        myconfig = Config(max_bear_deviation=10.0)
        reference = get_test_linelocation_3()
        decode(reference, self.reader, config=myconfig)
        too_strict_config = Config(max_bear_deviation=0.0)
        with self.assertRaises(LRDecodeError):
            decode(reference, self.reader, config=too_strict_config)

    def test_backtracking(self):
        myconfig = Config(search_radius=5, max_dnp_deviation=0.02)
        reference = get_test_linelocation_4()
        observer = SimpleObserver()
        location = decode(reference, self.reader, observer=observer, config=myconfig)
        lines = [l.line_id for l in location.lines]
        self.assertListEqual([20], lines)
        self.assertGreater(len(observer.failed_matches), 0)

    def tearDown(self):
        self.reader.connection.close()


class DecodingToolsTests(unittest.TestCase):
    def test_load_saved_config(self):
        "Save and load a Config object"
        test_config_file = StringIO()
        save_config(DEFAULT_CONFIG, test_config_file)
        test_config_file.seek(0)
        config = load_config(test_config_file)
        self.assertDictEqual(config.tolerated_lfrc, DEFAULT_CONFIG.tolerated_lfrc)
        self.assertEqual(config.bear_dist, DEFAULT_CONFIG.bear_dist)

    def test_remove_offsets(self):
        "Remove offsets containing lines"
        node0 = DummyNode(Coordinates(13.128987, 52.494595))
        node1 = DummyNode(extrapolate(node0.coord, 20, 180.0))
        node2 = DummyNode(extrapolate(node1.coord, 90, 90.0))
        node3 = DummyNode(extrapolate(node2.coord, 20, 180.0))
        lines = [
            DummyLine(0, node0, node1),
            DummyLine(1, node1, node2),
            DummyLine(2, node2, node3)
        ]
        route = Route(PointOnLine(lines[0], 0.5), [lines[1]], PointOnLine(lines[2], 0.5))
        route = remove_offsets(route, 40, 40)
        self.assertListEqual(route.lines, [lines[1]])
        self.assertAlmostEqual(route.length(), 30, delta=1)

    def test_remove_offsets_raises(self):
        "Remove too big offsets"
        node0 = DummyNode(Coordinates(13.128987, 52.494595))
        node1 = DummyNode(extrapolate(node0.coord, 10, 180.0))
        line = DummyLine(0, node0, node1)
        route = Route(PointOnLine(line, 0.0), [], PointOnLine(line, 1.0))
        with self.assertRaises(LRDecodeError):
            remove_offsets(route, 11, 0)
        with self.assertRaises(LRDecodeError):
            remove_offsets(route, 0, 11)
