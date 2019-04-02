"""Extensions to rekall.vgrid_utils especialized to Esper Database Schema.

Tracks:
    CaptionTrack: Add caption to the VBlocks. Works in either VideoVBlocks or
        IntervalVBlocks mode.
"""

from rekall.interval_set_3d import IntervalSet3D, Interval3D
from rekall.vgrid_utils.vblocks_builder import build_interval, DrawType_Caption
import esper.captions

class CaptionTrack:
    """Track for adding captions to vblocks.

    Works with either VideoVBlocksBuilder or IntervalVBlocksBuilder.

    Example of using with VideoVBlockBuilder:

    # face_collection is a DomainIntervalCollection of face intervals.

    # We want to see a list of VBlocks where each is a video in the collection
    # We want to see two tracks in each VBlock: one showing all faces in the
    # collection with bounding boxes drawn and a flag metadata set; another
    # showing all captions.

    json = VideoVBlocksBuilder()\\
        .add_track(
            VideoTrackBuilder('faces', face_collection)\\
                .set_draw_type(DrawType_Bbox())\\
                .add_metadata('flag', Metadata_Flag()))\\
        .add_track(CaptionTrack())\\
        .build()
    """
    def __init__(self):
        self.name = 'caption'
        self.video_ids = set([])
        self._cache = {}

    def build_for_video(self, video_id):
        if video_id in self._cache:
            return self._cache[video_id]
        ret = self._get_captions_for_video(video_id)
        self._cache[video_id] = ret
        return ret

    def build_for_interval(self, video_id, interval):
        return self.build_for_video(video_id)

    def _get_captions_for_video(self, video_id):
        """Returns the JSON intervals with the captions
        
        Note:
            The returned intervals use seconds on temporal dimension instead
            of frame number
        """
        subs = esper.captions.get_json(video_id)

        output = []
        for sub in subs:
            interval = Interval3D(
                    (sub['startTime'], sub['endTime']),
                    payload=sub['text'])
            output.append(build_interval(video_id, interval,
                DrawType_Caption(), {}))
        return output
