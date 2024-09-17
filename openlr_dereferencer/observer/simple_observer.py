"Contains a simple DecoderObserver implementation"
from typing import Sequence, NamedTuple, Optional
from openlr import LocationReferencePoint
from ..decoding.candidate import Candidate
from .abstract import DecoderObserver
from ..maps import Line


class AttemptedRoute(NamedTuple):
    """An attempted route between two lrps"""
    from_lrp: LocationReferencePoint
    to_lrp: LocationReferencePoint
    from_line: Line
    to_line: Line
    success: bool
    path: Optional[Sequence[Line]]
    reason: Optional[str]

class AttemptedMatch(NamedTuple):
    "An attempted try to resolve a pair of two LRPs"
    from_lrp: LocationReferencePoint
    to_lrp: LocationReferencePoint
    from_candidate: Sequence[Candidate]
    to_candidate: Sequence[Candidate]
    reason: Optional[str]


class SimpleObserver(DecoderObserver):
    """A simple observer that collects the information and can be
    queried after the decoding process is finished"""

    def __init__(self):
        self.candidates = {}
        self.failed_candidates = []
        self.attempted_routes = []
        self.failed_matches = []

    def on_candidate_found(self, lrp: LocationReferencePoint, candidate: Candidate):
        if lrp not in self.candidates:
            self.candidates[lrp] = [candidate]
        else:
            self.candidates[lrp].append(candidate)

    def on_candidate_rejected(self, lrp: LocationReferencePoint, candidate: Candidate, reason: str):
        self.failed_candidates.append(
            (lrp, candidate, reason)
        )

    def on_route_fail(self, from_lrp: LocationReferencePoint, to_lrp: LocationReferencePoint,
                      from_line: Line, to_line: Line, reason: str):
        self.attempted_routes.append(
            AttemptedRoute(from_lrp, to_lrp, from_line, to_line, False, None, reason)
        )

    def on_route_success(self, from_lrp: LocationReferencePoint, to_lrp: LocationReferencePoint,
                         from_line: Line, to_line: Line, path: Sequence[Line]):
        self.attempted_routes.append(
            AttemptedRoute(from_lrp, to_lrp, from_line, to_line, True, path, None)
        )

    def on_matching_fail(self, from_lrp: LocationReferencePoint, to_lrp: LocationReferencePoint,
                         from_candidates: Sequence[Candidate], to_candidates: Sequence[Candidate], reason: str):
        self.failed_matches.append(
            AttemptedMatch(from_lrp, to_lrp, from_candidates, to_candidates, reason)
        )