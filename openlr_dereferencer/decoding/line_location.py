"This module contains the LineLocation class and a builder function for it"

from typing import List, Iterable
from openlr import Coordinates, LineLocationReference
from ..maps import Line
from .path_math import remove_offsets
from .routes import Route, PointOnLine


class LineLocation:
    """A dereferenced line location. Create it from a combined Route which represents the
    line location path. The attribute `lines` is the list of involved `Line` elements.
    The attributes `p_off` and `n_off` contain the absolute offset at the first/last of these
    line elements. They are measured in meters.
    The method `coordinates()` returns the exact coordinates of the line location."""

    internal_route: Route

    def __init__(self, route: Route):
        self.internal_route = route

    def coordinates(self) -> List[Coordinates]:
        "Return the exact list of coordinates defining the line location path"
        return self.internal_route.coordinates()

    @property
    def lines(self) -> List[Line]:
        "The sequence of lines involved in this location"
        return self.internal_route.lines

    @property
    def p_off(self) -> float:
        "This location starts `p_off` meters into the first line"
        return self.internal_route.absolute_start_offset

    @property
    def n_off(self) -> float:
        "This location ends `n_off` meters before the last line"
        return self.internal_route.absolute_end_offset


def get_lines(line_location_path: Iterable[Route]) -> List[Line]:
    "Convert a line location path to its sequence of line elements"
    result = []
    for part in line_location_path:
        for line in part.lines:
            if result and result[-1].line_id == line.line_id:
                result.pop()
            result.append(line)
    return result


def combine_routes(line_location_path: Iterable[Route], equal_area: bool = False) -> Route:
    """Builds the whole location reference path

    Args:
        line_location_path:
            Consecutive Routes, like those partial routes resulting from matching an LRP list
            onto a map

    Returns:
        The combined route
    """
    path = get_lines(line_location_path)
    start = PointOnLine(path.pop(0), line_location_path[0].start.relative_offset, equal_area)
    if path:
        end = PointOnLine(path.pop(), line_location_path[-1].end.relative_offset, equal_area)
    else:
        end = PointOnLine(start.line, line_location_path[-1].end.relative_offset, equal_area)
    return Route(start, path, end)


def build_line_location(path: List[Route], reference: LineLocationReference, equal_area: bool = False) -> LineLocation:
    """Builds a LineLocation object from all location reference path parts and the offset values.

    The result will be a trimmed list of Line objects, with minimized offset values"""
    p_off = reference.poffs * path[0].length()
    n_off = reference.noffs * path[-1].length()
    return LineLocation(remove_offsets(combine_routes(path, equal_area), p_off, n_off, equal_area))
