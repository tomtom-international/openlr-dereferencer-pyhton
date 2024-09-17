"Contains the abstract observer class for the decoder"
from abc import abstractmethod
from typing import Sequence

from openlr import LocationReferencePoint

from ..decoding.candidate import Candidate
from ..maps import Line


class DecoderObserver:
    "Abstract class representing an observer to the OpenLR decoding process"

    @abstractmethod
    def on_candidate_found(self, lrp: LocationReferencePoint, candidate: Candidate):
        "Called by the decoder when it finds a candidate for a location reference point"

    @abstractmethod
    def on_candidate_rejected(self, lrp: LocationReferencePoint, candidate: Candidate, reason: str):
        "Called by the decoder when a candidate for a location reference point is rejected"

    @abstractmethod
    def on_route_success(self, from_lrp: LocationReferencePoint, to_lrp: LocationReferencePoint,
                         from_line: Line, to_line: Line, path: Sequence[Line]):
        """Called after the decoder successfully finds a route between two candidate
        lines for successive location reference points"""

    @abstractmethod
    def on_route_fail(self, from_lrp: LocationReferencePoint, to_lrp: LocationReferencePoint,
                      from_line: Line, to_line: Line, reason: str):
        """Called after the decoder fails to find a route between two candidate
        lines for successive location reference points"""

    def on_matching_fail(self, from_lrp: LocationReferencePoint, to_lrp: LocationReferencePoint,
                         from_candidates: Sequence[Candidate], to_candidates: Sequence[Candidate], reason: str):
        """Called after none of the candidate pairs for two LRPs were matching.
        
        The only way of recovering is to go back and discard the last bit of
        the dereferencedd line location, if possible."""
