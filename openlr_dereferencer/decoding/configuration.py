from typing import NamedTuple, List, Dict
from openlr import FRC, FOW

#: The default value for the `fow_standin_score` config option.
#: The values are adopted from the openlr Java implementation.
DEFAULT_FOW_STAND_IN_SCORE = [
    [0.50, 0.50, 0.50, 0.50, 0.50, 0.50, 0.50, 0.5],  # Undefined FOW
    [0.50, 1.00, 0.75, 0.00, 0.00, 0.00, 0.00, 0.0],  # Motorway
    [0.50, 0.75, 1.00, 0.75, 0.50, 0.00, 0.00, 0.0],  # Multiple carriage way
    [0.50, 0.00, 0.75, 1.00, 0.50, 0.50, 0.00, 0.0],  # Single carriage way
    [0.50, 0.00, 0.50, 0.50, 1.00, 0.50, 0.00, 0.0],  # Roundabout
    [0.50, 0.00, 0.00, 0.50, 0.50, 1.00, 0.00, 0.0],  # Traffic quare
    [0.50, 0.00, 0.00, 0.00, 0.00, 0.00, 1.00, 0.0],  # Sliproad
    [0.50, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 1.0],  # Other FOW
]

class Config(NamedTuple):
    "A config object provides all settings that influenec the decoder's behaviour"
    #: Configures the default radius to search for map objects around an LRP. This value is in meters.
    search_radius: float = 100.0
    #: Tolerable relative DNP deviation of a path
    #:
    #: A path may deviate from the DNP by this relative value plus TOLERATED_DNP_DEV in order to be
    #: considered. The value here is relative to the expected distance to next point.
    max_dnp_deviation: float = 0.3
    #: Additional buffer to the range of allowed path distance
    #:
    #: In order to be considered, a path must not deviate from the DNP value by more than
    #: MAX_DNP_DEVIATION (relative value) plus TOLERATED_DNP_DEV. This value is in meters.
    tolerated_dnp_dev: int = 30
    #: A filter for candidates with insufficient score. Candidates below this score are not considered
    min_score: float = 0.3
    #: For every LFRCNP possibly present in an LRP, this defines
    #: what lowest FRC in a considered route is acceptable
    tolerated_lfrc: Dict[FRC, FRC] = {frc:frc for frc in FRC}
    #: Partial candidate line threshold, measured in meters
    #:
    #: To find candidates, the LRP coordinates are projected against any line in the local area.
    #: If the distance from the starting point is greater than this threshold, the partial line
    #: beginning at the projection point is considered to be the candidate.
    candidate_threshold = 20
    #: Defines the weight the FOW score has on the overall score of a candidate.
    fow_weight: float = 1 / 4
    #: Defines the weight the FRC score has on the overall score of a candidate.
    frc_weight: float = 1 / 4
    #: Defines the weight the coordinate difference has on the overall score of a candidate.
    geo_weight: float = 1 / 4
    #: Defines the weight the bearing score has on the overall score of a candidate.
    bear_weight: float = 1 / 4
    #: When comparing an LRP FOW with a candidate's FOW, this matrix defines
    #: how well the candidate's FOW fits as replacement for the expected value.
    #: The usage is `FOW_SCORING[lrp's fow][candidate's fow]`.
    #: It returns the score.
    fow_standin_score: List[List[float]] = DEFAULT_FOW_STAND_IN_SCORE
    #: The bearing angle is computed along this distance on given line. Given in meters.
    bear_dist: int = 20

DEFAULT_CONFIG = Config()