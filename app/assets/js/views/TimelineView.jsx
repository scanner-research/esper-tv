import React from 'react';
import {boundingRect} from './FrameView.jsx';
import ClipView from './ClipView.jsx';
import {observer} from 'mobx-react';
import {toJS} from 'mobx';

@observer
class MarkerView extends React.Component {
  render() {
    let {t, w, h, mw, mh, mf, label, type, color, ..._} = this.props;
    let range = DISPLAY_OPTIONS.get('timeline_range');
    let time_to_x = (t) => w/2 + (t - this.props.currentTime) / (range/2) * w/2;
    let x = time_to_x(t);
    let margin = mw;
    if (0 <= x && x <= w) {
      if (type == 'open') {
        let points = `${mw*2},${margin} 0,${margin} 0,${mh-2*margin} ${mw*2},${mh-2*margin}`;
        return (<g transform={`translate(${x}, 0)`}>
          <polyline fill="none" stroke={color} strokeWidth={mw} points={points} />
          <text x={mw+4} y={h/2} alignmentBaseline="middle" fontSize={mf}>{label}</text>
        </g>);
      } else {
        let points = `${-mw*2},${margin} 0,${margin} 0,${mh-2*margin} ${-mw*2},${mh-2*margin}`;
        return (<g transform={`translate(${x}, 0)`}>
          <polyline fill="none" stroke={color} strokeWidth={mw} points={points} />
          <text x={-(mw+4)} y={h/2} alignmentBaseline="middle" textAnchor="end" fontSize={mf}>{label}</text>
        </g>);
      }
    } else {
      return <g />;
    }
  }
}

@observer
class TrackView extends React.Component {
  _mouseX = -1
  _mouseY = -1

  _onKeyPress = (e) => {
    if (IGNORE_KEYPRESS) {
      return;
    }

    let rect = boundingRect(this._g);
    let [x, y] = this._localCoords();
    if (!(0 <= x && x <= rect.width && 0 <= y && y <= rect.height)) {
      return;
    }

    let chr = String.fromCharCode(e.which);
    this.props.onKeyPress(chr, this.props.i);
  }

  _onMouseMove = (e) => {
    this._mouseX = e.clientX;
    this._mouseY = e.clientY;
  }

  _localCoords = (e) => {
    let rect = boundingRect(this._g);
    return [this._mouseX - rect.left, this._mouseY - rect.top];
  }

  componentDidMount() {
    document.addEventListener('keypress', this._onKeyPress);
    document.addEventListener('mousemove', this._onMouseMove);
  }

  componentWillUnmount() {
    document.removeEventListener('keypress', this._onKeyPress);
    document.removeEventListener('mousemove', this._onMouseMove);
  }

  render() {
    let {track, w, h, mw, mh, mf, video, ..._} = this.props;
    let label = track.gender_id;
    let identity = track.identity;
    let start = track.min_frame / video.fps;
    let end = track.max_frame / video.fps;

    let range = DISPLAY_OPTIONS.get('timeline_range');
    let time_to_x = (t) => w/2 + (t - this.props.currentTime) / (range/2) * w/2;
    let x1 = time_to_x(start);
    let x2 = time_to_x(end);

    let ident_colors = window.search_result.labeler_colors
    let color = DISPLAY_OPTIONS.get('track_color_identity')
         ? ident_colors[identity % ident_colors.length]
         : window.search_result.gender_colors[window.search_result.genders[label].name];

    return (
      <g ref={(n) => {this._g = n;}}>
        <rect x={x1} width={x2-x1} y={0} height={h} fill={color} />
        {range < 600
         ? <g>
           <line x1={x1} y1={0} x2={x1} y2={h} stroke="black" />
           <line x1={x2} y1={0} x2={x2} y2={h} stroke="black" />
           {identity !== undefined
            ? <text x={x1+2} y={h/2} textAnchor="start" alignmentBaseline="middle">{identity}</text>
            : <g />}
         </g>
         : <g />}
      </g>
    );
  }
}

@observer
export default class TimelineView extends React.Component {
  state = {
    currentTime: 0,
    clickedTime: -1,
    displayTime: -1,
    startX: -1,
    startY: -1,
    trackStart: -1
  }

  _videoPlaying = false;
  _lastPlaybackSpeed = DISPLAY_OPTIONS.get('playback_speed');
  _undoStack = [];

  _onTimeUpdate = (t) => {
    this.setState({currentTime: t});
  }

  _localCoords = (e) => {
    let rect = boundingRect(this._svg);
    return [e.clientX - rect.left, e.clientY - rect.top];
  }

  _onMouseDown = (e) => {
    let [x, y] = this._localCoords(e);
    this.setState({startX: x, startY: y, clickedTime: this.state.currentTime});
  }

  _onMouseMove = (e) => {
    if (this.state.startX != -1) {
      let [x, y] = this._localCoords(e);
      let dx = x - this.state.startX;
      let dt = DISPLAY_OPTIONS.get('timeline_range') * dx / boundingRect(this._svg).width * -1;
      this.setState({
        displayTime: this.state.clickedTime + dt,
        currentTime: this.state.clickedTime + dt
      });
    }
  }

  _onMouseUp = (e) => {
    this.setState({startX: -1, startY: -1});
  }

  _onMouseLeave = (e) => {
    if (this.state.startX != -1) {
      this.setState({startX: -1, startY: -1});
    }
  }

  _video = () => {
    return window.search_result.videos[this.props.group.elements[0].video];
  }

  _onVideoPlay = () => {
    this._videoPlaying = true;
  }

  _onVideoStop = () => {
    this._videoPlaying = false;
  }

  _pushState = () => {
    this._undoStack.push(_.cloneDeep(toJS(this.props.group.elements)));

    // Keep the stack small to avoid using too much memory
    let MAX_UNDO_STACK_SIZE = 10;
    if (this._undoStack.length > MAX_UNDO_STACK_SIZE) {
      this._undoStack.shift();
    }
  }

  _onTrackKeyPress = (e, i) => {
    let chr = String.fromCharCode(e.which);
    if (chr == 'g') {
      this._pushState();
      let track = this.props.group.elements[i];
      let keys = _.sortBy(_.map(_.keys(window.search_result.genders), (x) => parseInt(x)));
      track.gender_id = keys[(_.indexOf(keys, track.gender_id) + 1) % keys.length];
    }

    else if (chr == 'm') {
      this._pushState();
      this.props.group.elements[i-1].max_frame = this.props.group.elements[i].max_frame;
      this.props.group.elements.splice(i, 1);
    }

    else if (chr == 'd') {
      this._pushState();
      this.props.group.elements.splice(i, 1);
    }
  }

  _onKeyPress = (e) => {
    if (IGNORE_KEYPRESS || !this._videoPlaying) {
      return;
    }

    let chr = String.fromCharCode(e.which);

    let fps = this._video().fps;
    let curFrame = this.state.currentTime * fps;
    let elements = this.props.group.elements;
    if (chr == '\r') {
      let lastTrack = elements.map((clip, i) => [clip, i]).filter(([clip, _]) =>
        clip.min_frame <= curFrame);
      let offset = e.shiftKey ? -1 : 1;
      let index = lastTrack[lastTrack.length - 1][1] + offset;
      if (0 <= index && index < elements.length) {
        let newTime = elements[index].min_frame / fps + 0.1;
        this.setState({
          displayTime: newTime,
          currentTime: newTime
        });
      }
    }

    else if (chr == 'r') {
      let playbackSpeed = DISPLAY_OPTIONS.get('playback_speed');
      if (playbackSpeed != 1) {
        DISPLAY_OPTIONS.set('playback_speed', 1);
        this._lastPlaybackSpeed = playbackSpeed;
      } else {
        DISPLAY_OPTIONS.set('playback_speed', this._lastPlaybackSpeed);
      }
    }

    else if (chr == 't') {
      if (this.state.trackStart == -1) {
        this.setState({trackStart: this.state.currentTime});
      } else {
        this._pushState();

        let start = Math.round(this.state.trackStart * fps);
        let end = Math.round(this.state.currentTime * fps);

        let to_add = [];
        let to_delete = [];
        elements.map((clip, i) => {
          // +++ is the new clip, --- is old clip, overlap prioritized to new clip

          // [---[++]+++]
          if (clip.min_frame <= start && start <= clip.max_frame && clip.max_frame <= end) {
            clip.max_frame = start;
          }

          // [+++[+++]---]
          else if(start <= clip.min_frame && clip.min_frame <= end && end <= clip.max_frame){
            clip.min_frame = end;
          }

          // [---[+++]---]
          else if (clip.min_frame <= start && end <= clip.max_frame) {
            let new_clip = _.clone(clip);
            new_clip.min_frame = end;
            clip.max_frame = start;
            to_add.push(new_clip);
          }

          // [+++[+++]+++]
          else if (start <= clip.min_frame && clip.max_frame <= end) {
            to_delete.push(i);
          }
        });

        _.reverse(to_delete);
        to_delete.map((i) => elements.splice(i, -1));
        elements.push.apply(elements, to_add);
        elements.push({
          video: elements[0].video,
          min_frame: start,
          max_frame: end,
          gender_id: _.find(window.search_result.genders, (l) => l.name == 'M').id
        });
        this.props.group.elements = _.sortBy(elements, ['min_frame']);

        this.setState({trackStart: -1});
      }
    }

    else if (chr == 'z') {
      if (this._undoStack.length > 0) {
        let lastState = this._undoStack.pop();
        this.props.group.elements = lastState;
      }
    }

    else {
      let curTracks = this.props.group.elements.map((clip, i) => [clip, i]).filter(([clip, _]) =>
        clip.min_frame <= curFrame && curFrame <= clip.max_frame);
      if (curTracks.length == 0) {
        console.warn('No tracks to process');
      } else if (curTracks.length > 1) {
        console.error('Attempting to process multiple tracks');
      } else {
        this._onTrackKeyPress(e, curTracks[0][1]);
      }
    }
  }

  componentDidMount() {
    document.addEventListener('keypress', this._onKeyPress);
    this.setState({
      currentTime: this.props.group.elements[0].min_frame / this._video().fps
    })
  }

  componentWillUnmount() {
    document.removeEventListener('keypress', this._onKeyPress);
  }

  // TODO(wcrichto): timeline disappears after deleting first track in the timeline

  render() {
    let group = this.props.group;
    let expand = this.props.expand;

    let clip = {
      video: group.elements[0].video,
      min_frame: group.elements[0].min_frame,
      max_frame: group.elements[group.elements.length-1].max_frame
    };

    let video = this._video();
    let small_height = expand ? video.height : 100 * DISPLAY_OPTIONS.get('thumbnail_size');
    let small_width = video.width * small_height / video.height;

    let style = {
      width: small_width,
    };

    let timeboxStyle = {
      width: small_width,
      height: expand ? 60 : 20
    }

    let tprops = {
      w: timeboxStyle.width,
      h: timeboxStyle.height,
      mw: expand ? 4 : 2,
      mh: timeboxStyle.height,
      mf: expand ? 16 : 12,
      currentTime: this.state.currentTime,
      video: video
    };

    return (<div className='timeline' style={style}>
      <ClipView clip={clip} onTimeUpdate={this._onTimeUpdate} showMeta={false}
                expand={this.props.expand} displayTime={this.state.displayTime}
                onVideoPlay={this._onVideoPlay}
                onVideoStop={this._onVideoStop} />
      <svg className='time-container' style={timeboxStyle} onMouseDown={this._onMouseDown}
           onMouseMove={this._onMouseMove}
           onMouseUp={this._onMouseUp}
           onMouseLeave={this._onMouseLeave}
           ref={(n) => {this._svg = n;}}>
        <g>{group.elements.map((track, i) =>
          <TrackView key={i} i={i} track={track} onKeyPress={this._onTrackKeyPress} {...tprops} />)}
        </g>
        {this.state.trackStart != -1
         ? <MarkerView t={this.state.trackStart} type="open" color="rgb(230, 230, 20)" {...tprops} />
         : <g />}
        <line x1={tprops.w/2} x2={tprops.w/2} y1={0} y2={tprops.h} stroke="rgb(20, 230, 20)" strokeWidth={tprops.mw*1.5} />
        <MarkerView t={clip.min_frame/video.fps} type="open" color="black" {...tprops} />
        <MarkerView t={clip.max_frame/video.fps} type="close" color="black"  {...tprops} />
      </svg>
    </div>);
  }
}
