"""Utilities for building VGrid inputs from Rekall interval sets

VGrid displays a list of VBlocks. Each VBlock can have multiple tracks, and
each track shows a timeline of intervals in that track, as well as drawing
objects and showing metadata of the interval as configured.

There are two main use cases of VGrid:
    1. VideoVBlocks. This mode displays a VBlock for each video. Each track
        in the VBlock is an IntervalSet to visualize in that video.
    2. IntervalVBlocks. This mode displays a VBlock for each interval/clip.
        Each track in the VBlock is an IntervalSet to visualize in that
        interval/clip.

The VBlocksBuilders in this module helps building the JSON structure for this
list of VBlocks.

Example of using VideoVBlock:

    # face_collection is a DomainIntervalCollection of face intervals.

    # We want to see a list of VBlocks where each is a video in the collection
    # We want to see two tracks in each VBlock: one showing all faces in the
    # collection with bounding boxes drawn and a flag metadata set; another
    # showing all captions of the video.

    json = VideoVBlocksBuilder()\\
        .add_track(
            VideoTrackBuilder('faces', face_collection)\\
                .set_draw_type(DrawType_Bbox())\\
                .add_metadata('flag', Metadata_Flag()))\\
        .add_track(
            CaptionTrack())\\
        .build()

Example of using IntervalBlock:

    # conversations_with_ids is a DomainIntervalCollection of conversation
    # sequences, where the payload on each conversation is an IntervalSet of
    # face bounding boxes with identity as payload.

    # We want to see a list of VBlocks where each is a conversation 
    # sequence in the collection. We want to see two tracks in each VBlock:
    # one showing the conversation sequence; another showing all the faces with
    # the bounding boxes drawn and generic metadata showing the identities.

    json = IntervalVBlocksBuilder()\\
        .add_track(
            IntervalTrackBuilder('conversation'))\\
        .add_track(
            IntervalTrackBuilder('faces', lambda i:i.payload)\\
                    .set_draw_type(DrawType_Bbox())\\
                    .add_metadata('identity', Metadata_Generic()))\\
        .build(conversations_with_ids)

Symbols exported in this module are the following.

VBlocksBuilders:
    VideoVBlocksBuilder: VideoVBlocks mode.
    IntervalVBlocksBuilder: IntervalVBlocks mode.

Tracks:
    VideoTrackBuilder: Build custom tracks for VideoVBlocks mode.
    IntervalTrackBuilder: Build custom tracks for IntervalVBlocks mode.
    CaptionTrack: Add caption to the VBlocks. Works in either mode.

DrawTypes:
    DrawType_Bbox: Draw bounding boxes around the spatial dimension.
    DrawType_Caption: Display text in the caption box.

Metadatas:
    Metadata_Flag: Plant a flag marking the temporal interval.
    Metadata_Generic: Show a generic JSON text.
"""

from rekall.interval_set_3d import IntervalSet3D, Interval3D
import esper.captions

class VideoVBlocksBuilder:
    """Builder of a list of VBlocks, one for each video."""
    def __init__(self):
        self._tracks = {}
        self._video_ids = set([])

    def add_track(self, track):
        """Adds a track to vblocks.
        
        Args:
            track (VideoTrackBuilder): the track to add

        Returns:
            self for chaining
        """
        self._tracks[track.name] = track
        self._video_ids.update(track.video_ids)
        return self

    def build(self):
        """Builds the JSON list of vblocks to feed into VGrid."""
        return [{
                    name: track.build_for_video(vid)
                    for name, track in self._tracks.items()
                } for vid in self._video_ids]

class _CustomTrackMixin:
    """Mixin for a TrackBuilder that allows custom draw type and metadata"""
    
    def set_draw_type(self, draw_type):
        """Set the type of visualization to draw for this track.

        VGrid will draw the visualization for each interval in this track.

        Args:
            draw_type: A function that takes video_id and Interval3D, and
                returns the JSON of the object to draw.

        Returns:
            self for chaining
        """
        self._draw_type = draw_type
        return self

    def add_metadata(self, name, metadata):
        """Add a named metadata to this track.

        VGrid will display the metadata for each interval in this track.

        Args:
            name (string): Name of the metadata
            metadata: A function that takes video_id and Interval3D, and
                returns the JSON of the metadata to display.

        Returns:
            self for chaining
        """
        self._metadatas[name] = metadata
        return self

    def _build_interval(self, video_id, interval):
        """Helper to build a JSON interval in this track."""
        return {
            "bounds": _bounds_in_json(video_id, interval),
            "draw_type": self._draw_type(video_id, interval),
            "metadata": {
                name: metadata(video_id, interval)
                for name, metadata in self._metadatas.items()
            }
        }


class VideoTrackBuilder(_CustomTrackMixin):
    """Builder of a track for some collection of videos from IntervalSet3D.
    
    Attributes:
        name (string): Name of the track
        video_ids (Set[int]): Videos that should have this track.
    """
    def __init__(self, name, collection):
        """Initializer

        Args:
            name (string): Name of the track
            collection (DomainVideoCollection): intervals grouped by video_ids
                from which to build the visualization track
        """
        self.name = name
        self.video_ids = set(collection.keys())

        self._collection = collection
        self._draw_type = lambda *args: None
        self._metadatas = {}

    def build_for_video(self, video_id):
        """Builds list of JSON intervals for the track on one VBlock/Video."""
        intervalset = self._collection[video_id]
        return [self._build_interval(video_id, interval)
                for interval in intervalset.get_intervals()]

class IntervalVBlocksBuilder:
    """Builder of a list of VBlocks, one for each interval."""
    def __init__(self):
        self._tracks = {}

    def add_track(self, track):
        """Adds a track to each vblock

        Args:
            track (IntervalTrackBuilder): the track to add

        Returns:
            self for chaining
        """
        self._tracks[track.name] = track
        return self

    def build(self, collection):
        """Builds the JSON list of vblocks to feed into VGrid."""
        output = []
        for video_id, intervals in collection.items():
            for interval in intervals.get_intervals():
                output.append({
                    name: track.build_for_interval(video_id, interval)
                    for name, track in self._tracks.items()
                })
        return output

class IntervalTrackBuilder(_CustomTrackMixin):
    """Builder of a track for single-interval vblocks.
    
    Attributes:
        name (string): Name of the track
    """
    def __init__(self, name, intervalset_getter=lambda i: IntervalSet3D([i])):
        """Initializer

        Args:
            name (string): Name of the track
            intervalset_getter (optional): A function that takes an Interval3D
            and returns the IntervalSet3D to visualize for that vblock.
            Defaults to the intervalset with only the vblock interval.
        """
        self.name = name

        self._intervalset_getter = intervalset_getter
        self._draw_type = lambda *args: None
        self._metadatas = {}

    def build_for_interval(self, video_id, interval):
        """Builds list of JSON intervals for the track for one Interval."""
        intervalset = self._intervalset_getter(interval)
        return [self._build_interval(video_id, interval)
                for interval in intervalset.get_intervals()]

class CaptionTrack:
    """Track for adding captions to vblocks.

    Can act as either IntervalTrackBuilder or VideoTrackBuilder.
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
            output.append({
                "bounds": _bounds_in_json(video_id, interval),
                "draw_type": DrawType_Caption()(video_id, interval),
                "metadata": {}
            })
        return output

def _bounds_in_json(video_id, interval):
    """Returns a JSON object for interval bounds in VGrid."""
    return {
        "domain": _video_domain_in_json(video_id),
        "t1": interval.t[0],
        "t2": interval.t[1],
        "bbox": _bbox_in_json(interval),
    }

def _video_domain_in_json(video_id):
    """Returns a JSON  Domain_Video object."""
    return {
        "type": "Domain_Video",
        "value": {
            "video_id": video_id
        },
    }

def _bbox_in_json(interval):
    """Returns a JSON BoundingBox object."""
    return {
        "x1": interval.x[0],
        "x2": interval.x[1],
        "y1": interval.y[0],
        "y2": interval.y[1],
    }

def _get_payload(i):
    return i.payload

class DrawType_Caption:
    """A DrawType for displaying text in caption box"""
    def __init__(self, get_caption=_get_payload):
        """Initialize

        Args:
            get_caption (optional): A function from Interval3D to caption.
                Defaults to the payload field
        """
        self._get_caption = get_caption

    def __call__(self, video_id, interval):
        return {
            "type": "DrawType_Caption",
            "value": {
                "text": self._get_caption(interval)    
            },                    
        }

class DrawType_Bbox:
    """A DrawType for drawing bounding boxes around spatial extent"""
    def __call__(self, video_id, interval):
        return {"type": "DrawType_Bbox"}

class Metadata_Flag:
    """A Metadata that flags the interval on the Timeline."""
    def __call__(self, video_id, interval):
        return {"type": "Metadata_Flag"}

class Metadata_Generic:
    """A Metadata that stores generic JSON"""
    def __init__(self, getter=_get_payload):
        """Initialize

        Args:
            getter (optional): A function from Interval3D to the generic
                metadata.
                Defaults to the payload field
        """
        self._getter = getter

    def __call__(self, video_id, interval):
        return {
            "type": "Metadata_Generic",
            "value": {
                "data": self._getter(interval)    
            }
        }



