"""The one measurement type every matcher produces: a source point paired with a reference point."""


class Match:
    def __init__(self, source_xy, reference_xy, confidence):
        self.source_xy = source_xy
        self.reference_xy = reference_xy
        self.confidence = confidence
