"Contains the Node and the Line class of the example format"

from itertools import chain
from typing import Iterable
from openlr import Coordinates, FRC, FOW
from shapely.geometry import LineString
from openlr_dereferencer.maps import Line as AbstractLine, Node as AbstractNode

class Line(AbstractLine):
    "Line object implementation for the example format"

    def __init__(self, map_reader, line_id: int):
        if not isinstance(line_id, int):
            raise ExampleMapError(f"Line id '{line_id}' has confusing type {type(line_id)}")
        self.map_reader = map_reader
        self.line_id_internal = line_id

    def __repr__(self):
        return f"Line with id={self.line_id} of length {self.length}"

    @property
    def line_id(self) -> int:
        "Returns the line id"
        return self.line_id_internal

    @property
    def start_node(self) -> "Node":
        "Returns the node from which this line comes from"
        stmt = "SELECT startnode FROM openlr_lines WHERE line_id = %s"
        self.map_reader.cursor.execute(stmt, (self.line_id,))
        (point_id,) = self.map_reader.cursor.fetchone()
        return self.map_reader.get_node(point_id)

    @property
    def end_node(self) -> "Node":
        "Returns the node to which this line goes"
        stmt = "SELECT endnode FROM openlr_lines WHERE line_id = %s"
        self.map_reader.cursor.execute(stmt, (self.line_id,))
        (point_id,) = self.map_reader.cursor.fetchone()
        return self.map_reader.get_node(point_id)

    @property
    def fow(self) -> FOW:
        "Returns the form of way for this line"
        stmt = "SELECT fow FROM openlr_lines WHERE line_id = %s"
        self.map_reader.cursor.execute(stmt, (self.line_id,))
        (fow,) = self.map_reader.cursor.fetchone()
        return FOW(fow)

    @property
    def frc(self) -> FRC:
        "Returns the functional road class for this line"
        stmt = "SELECT frc FROM openlr_lines WHERE line_id = %s"
        self.map_reader.cursor.execute(stmt, (self.line_id,))
        (frc,) = self.map_reader.cursor.fetchone()
        return FRC(frc)

    @property
    def geometry(self) -> LineString:
        "Returns the line geometry"
        points = [self.point_n(index + 1) for index in range(self.num_points())]
        return LineString(points)

    def distance_to(self, coord) -> float:
        "Returns the distance of this line to `coord` in meters"
        stmt = """
            SELECT
                ST_Distance(
                    ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, 
                    path::geography
                )
            FROM openlr_lines 
            WHERE
                line_id = %s;
        """
        cur = self.map_reader.cursor
        cur.execute(stmt, (coord.lon, coord.lat, self.line_id))
        (dist,) = cur.fetchone()
        if dist is None:
            return 0.0
        return dist

    def num_points(self) -> int:
        "Returns how many points the path geometry contains"
        stmt = "SELECT ST_NumPoints(path) FROM openlr_lines WHERE line_id = %s"
        self.map_reader.cursor.execute(stmt, (self.line_id,))
        (count,) = self.map_reader.cursor.fetchone()
        return count

    def point_n(self, index) -> Coordinates:
        "Returns the `n` th point in the path geometry, starting at 0"
        stmt = "SELECT ST_X(ST_PointN(path, %s)), ST_Y(ST_PointN(path, %s)) FROM openlr_lines WHERE line_id = %s"
        self.map_reader.cursor.execute(stmt, (index, index, self.line_id))
        (lon, lat) = self.map_reader.cursor.fetchone()
        if lon is None or lat is None:
            raise Exception(f"line {self.line_id} has no point {index}!")
        return Coordinates(lon, lat)

    def near_nodes(self, distance):
        "Yields every point within a certain distance, in meters."
        stmt = """
            SELECT
                openlr_nodes.node_id
            FROM openlr_nodes,openlr_lines
            WHERE
                openlr_lines.line_id = %s AND 
                ST_Distance(
                    openlr_nodes.coord::geography,
                    openlr_lines.path::geography
                )<= %s
        """
        self.map_reader.cursor.execute(stmt, (self.line_id, distance))
        for (point_id,) in self.map_reader.cursor.fetchall():
            yield self.map_reader.get_node(point_id)

    @property
    def length(self) -> float:
        "Length of line in meters"
        stmt = "SELECT ST_Length(path::geography) FROM openlr_lines WHERE line_id = %s"
        self.map_reader.cursor.execute(stmt, (self.line_id,))
        (result,) = self.map_reader.cursor.fetchone()
        return result


class Node(AbstractNode):
    "Node class implementation for example_sqlite_map"

    def __init__(self, map_reader, node_id: int):
        if not isinstance(node_id, int):
            raise ExampleMapError(f"Node id '{id}' has confusing type {type(node_id)}")
        self.map_reader = map_reader
        self.node_id_internal = node_id

    @property
    def node_id(self):
        return self.node_id_internal

    @property
    def coordinates(self) -> Coordinates:
        stmt = "SELECT ST_X(coord), ST_Y(coord) FROM openlr_nodes WHERE node_id = %s"
        self.map_reader.cursor.execute(stmt, (self.node_id,))
        geo = self.map_reader.cursor.fetchone()
        return Coordinates(lon=geo[0], lat=geo[1])

    def outgoing_lines(self) -> Iterable[Line]:
        stmt = "SELECT line_id FROM openlr_lines WHERE startnode = %s"
        self.map_reader.cursor.execute(stmt, (self.node_id,))
        for (line_id,) in self.map_reader.cursor.fetchall():
            yield Line(self.map_reader, line_id)

    def incoming_lines(self) -> Iterable[Line]:
        stmt = "SELECT line_id FROM openlr_lines WHERE endnode = %s"
        self.map_reader.cursor.execute(stmt, [self.node_id])
        for (line_id,) in self.map_reader.cursor.fetchall():
            yield Line(self.map_reader, line_id)

    def connected_lines(self) -> Iterable[Line]:
        return chain(self.incoming_lines(), self.outgoing_lines())


class ExampleMapError(Exception):
    "Some error reading the DB"
