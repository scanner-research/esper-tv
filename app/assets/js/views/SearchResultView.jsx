import React from 'react';
import * as Rb from 'react-bootstrap';
import {observer} from 'mobx-react';
import {observable, autorun, toJS} from 'mobx';
import {Box, FrameView} from './FrameView.jsx';
import axios from 'axios';

let displayOptions = JSON.parse(localStorage.getItem("displayOptions") || JSON.stringify({
  results_per_page: 50,
  annotation_opacity: 1.0,
  show_pose: true,
  show_face: true,
  show_hands: true,
  show_lr: false,
  crop_bboxes: false,
  playback_speed: 1.0,
  show_middle_frame: true,
  show_gender_as_border: true,
  show_inline_metadata: false,
  thumbnail_size: 1
}));

window.DISPLAY_OPTIONS = observable.map(displayOptions);
window.IGNORE_KEYPRESS = false;

autorun(() => {
  localStorage.displayOptions = JSON.stringify(toJS(window.DISPLAY_OPTIONS));
});

@observer
class GroupsView extends React.Component {
  state = {
    page: 0,
    selected_start: -1,
    selected_end: -1,
    ignored: new Set(),
    positive_ex: new Set(),
    negative_ex: new Set()
  }

  _lastResult = window.search_result.result;

  constructor() {
    super();
    document.addEventListener('keypress', this._onKeyPress);
  }

  getColorClass(i){
    if (this.state.ignored.has(i)) {
      return 'ignored ';
    } else if (this.state.selected_start == i || (this.state.selected_start <= i && i <= this.state.selected_end)){
      return 'selected ';
    } else if (this.state.positive_ex.has(i)){
      return 'positive ';
    } else if (this.state.negative_ex.has(i)){
      return 'negative ';
    }
  }

  _onKeyPress = (e) => {
    let chr = String.fromCharCode(e.which);
    if (chr == 'a') {
      if (this.state.selected_start == -1) {
        return;
      }

      let green = this.state.positive_ex;

      let labeled = [];
      let end = this.state.selected_end == -1 ? this.state.selected_start : this.state.selected_end;
      for (let i = this.state.selected_start; i <= end; i++) {
        if (this.state.ignored.has(i)) {
          continue;
        }

        let frame = window.search_result.result[i].elements[0];
        labeled.push([frame.video, frame.start_frame, frame.objects]);
        green.add(i);
      }

      axios
        .post('/api/labeled', {dataset: DATASET, frames: labeled})
        .then(((response) => {
          console.log('Done!');
          this.setState({
            positive_ex: green,
            selected_start: -1,
            selected_end: -1
          });
        }).bind(this));
    }
  }

  _onSelect = (e) => {
    if (this.state.selected_start == -1){
      this.setState({
        selected_start: e
      });
    } else if (e == this.state.selected_start) {
      this.setState({
        selected_start: -1,
        selected_end: -1
      });
    } else {
      if (e < this.state.selected_start) {
        if (this.state.selected_end == -1) {
          this.setState({
            selected_end: this.state.selected_start
          });
        }
        this.setState({
          selected_start: e
        });
      } else {
        this.setState({
          selected_end: e
        });
      }
    }
  }

  _onIgnore = (e) => {
    if (this.state.ignored.has(e)) {
      this.state.ignored.delete(e);
    } else {
      this.state.ignored.add(e);
    }
    this.forceUpdate();
  }

  _numPages = () => {
    return Math.floor((window.search_result.result.length - 1)/ DISPLAY_OPTIONS.get('results_per_page'));
  }

  _prevPage = (e) => {
    e.preventDefault();
    this.setState({page: Math.max(this.state.page - 1, 0)});
  }

  _nextPage = (e) => {
    e.preventDefault();
    this.setState({page: Math.min(this.state.page + 1, this._numPages())});
  }

  componentDidUpdate() {
    if (window.search_result.result != this._lastResult) {
      this._lastResult = window.search_result.result;
      this.setState({
        page: 0,
        positive_ex: new Set(),
        negative_ex: new Set(),
        ignored: new Set(),
        selected_start: -1,
        selected_end: -1
      });
    }
  }

  render () {
    return (
      <div className='groups'>
        <div>
          {_.range(DISPLAY_OPTIONS.get('results_per_page') * this.state.page,
                   Math.min(DISPLAY_OPTIONS.get('results_per_page') * (this.state.page + 1),
                            window.search_result.result.length))
            .map((i) => <GroupView key={i} group={window.search_result.result[i]} group_id={i} onSelect={this._onSelect}
                                   onIgnore={this._onIgnore} colorClass={this.getColorClass(i)}/>)}
          <div className='clearfix' />
        </div>
        <div className='page-buttons'>
          <Rb.ButtonGroup>
            <Rb.Button onClick={this._prevPage}>&larr;</Rb.Button>
            <Rb.Button onClick={this._nextPage}>&rarr;</Rb.Button>
            <span className='page-count'>{this.state.page + 1}/{this._numPages() + 1}</span>
          </Rb.ButtonGroup>
        </div>
      </div>
    );
  }

}

// Displays results with basic pagination
@observer
class GroupView extends React.Component {
  render () {
    let group = this.props.group;
    return (
      <div className={'group selected ' + group.type}>
        <div>
          <div className='group-label'>{group.label}</div>
          <div className='group-elements'>
            {group.elements.map((clip, i) =>
              <ClipView key={i} clip={clip} group_id={this.props.group_id} onSelect={this.props.onSelect}
                        onIgnore={this.props.onIgnore} colorClass={this.props.colorClass}/>)}
            <div className='clearfix' />
          </div>
        </div>
      </div>
    );
  }
}


@observer
class ClipView extends React.Component {
  state = {
    showVideo: false,
    loadingVideo: false,
    expand: false,
    loopVideo: false
  }

  fullScreen = false
  frames = []

  constructor() {
    super();
    document.addEventListener('webkitfullscreenchange', this._onFullScreen);
  }

  _onFullScreen = () => {
    this.fullScreen = !this.fullScreen;

    if (this.fullScreen && this.state.showVideo) {
      this._video.currentTime = this._toSeconds(this.props.clip.start_frame);
      this._video.pause();
      setTimeout(() => {
        if (this._video) {
          this._video.play();
        }
      }, 1000);
    }
  }

  _onKeyPress = (e) => {
    if (IGNORE_KEYPRESS) {
      return;
    }

    let chr = String.fromCharCode(e.which);
    if (chr == 'p') {
      this.setState({
        showVideo: false,
        loadingVideo: true,
        loopVideo: false
      });
    } else if (chr == 'l') {
      this.setState({
        showVideo: false,
        loadingVideo: true,
        loopVideo: true
      });
    } else if (chr == 'f') {
      this.setState({expand: !this.state.expand});
    } else if (chr == 's') {
      this.props.onSelect(this.props.group_id);
    } else if (chr == 'x') {
      this.props.onIgnore(this.props.group_id);
    } else if (chr == 'y') {
      if (this.state.expand) {
        let frame = this._fromSeconds(this._video.currentTime);
        this.frames.push(frame);
        console.log(JSON.stringify(this.frames));
      }
    }
  }

  _onMouseEnter = () => {
    document.addEventListener('keypress', this._onKeyPress);
  }

  _onMouseLeave = () => {
    document.removeEventListener('keypress', this._onKeyPress);

    if (!this.state.expand) {
      if (this._video) {
        this._video.removeEventListener('seeked', this._onSeeked);
        this._video.removeEventListener('loadeddata', this._onLoadedData);
        this._video.removeEventListener('timeupdate', this._onTimeUpdate);
        this._video = null;
        this.frames = [];
      }
      this.setState({showVideo: false, loadingVideo: false});
    }
  }

  _onClick = () => {
    //console.log('Clicked SearchResultView', this.props.clip.objects[0].id);
  }

  _toSeconds = (frame) => {
    return frame / this._videoMeta().fps;
  }

  _fromSeconds = (sec) => {
    return Math.floor(sec * this._videoMeta().fps);
  }

  _onSeeked = () => {
    this.setState({showVideo: true, loadingVideo: false});
  }

  _onLoadedData = () => {
    this._video.currentTime = this._toSeconds(this.props.clip.start_frame);
    if (this._video.textTracks.length > 0) {
      this._video.textTracks[0].mode = 'showing';
    }
    this._video.play();
  }

  _onTimeUpdate = () => {
    if (this.state.loopVideo &&
        this.props.clip.end_frame !== undefined &&
        this._video.currentTime >= this._toSeconds(this.props.clip.end_frame)) {
      this._video.currentTime = this._toSeconds(this.props.clip.start_frame);
    }
  }

  componentDidUpdate() {
    if (this._video) {
      this._video.addEventListener('seeked', this._onSeeked);
      this._video.addEventListener('loadeddata', this._onLoadedData);
      this._video.addEventListener('timeupdate', this._onTimeUpdate);
    }
  }

  _videoMeta = () => {
    return window.search_result.videos[this.props.clip.video];
  }

  componentWillReceiveProps(props) {
    if (this.props.clip != props.clip) {
      this.setState({expand: false});
    }
  }

  componentWillUnmount() {
    document.removeEventListener('keypress', this._onKeyPress);
  }

  render() {
    let clip = this.props.clip;
    let video = this._videoMeta();

    let display_frame =
      DISPLAY_OPTIONS.get('show_middle_frame') && clip.end_frame
      ? Math.round((clip.end_frame + clip.start_frame) / 2)
      : clip.start_frame;
    let path = `/frameserver/fetch?path=${encodeURIComponent(video.path)}&frame=${display_frame}`;

    let meta = [];

    if (this.state.expand) {
      meta.push(['Video', `${video.path.split(/[\\/]/).pop()} (${video.id})`]);
      meta.push(['Frame', `${display_frame}`]);
    }

    if (clip.end_frame !== undefined) {
      let duration = (clip.end_frame - clip.start_frame) / video.fps;
      meta.push(['Duration', `${duration.toFixed(1)}s`]);
    }

    meta.push(['# objects', `${clip.objects.length}`]);

    if (clip.metadata !== undefined) {
      clip.metadata.forEach((entry) => {
        meta.push([entry[0], entry[1]]);
      });
    }

    let meta_per_row = this.state.expand ? 4 : 2;
    let td_style = {width: `${100 / meta_per_row}%`};

    if (this._video) {
      this._video.playbackRate = DISPLAY_OPTIONS.get('playback_speed');
    }

    let small_height = this.state.expand ? video.height : 100 * DISPLAY_OPTIONS.get('thumbnail_size');
    let small_width = video.width * small_height / video.height;
    let vidStyle = this.state.showVideo ? {
      zIndex: 2,
      width: small_width,
      height: small_height
    } : {};

    return (
      <div className={`search-result ${this.props.colorClass} ${(this.state.expand ? 'expanded' : '')}`}
           onMouseEnter={this._onMouseEnter}
           onMouseLeave={this._onMouseLeave}
           onClick={this._onClick}>
        <div className='media-container'>
          {this.state.loadingVideo || this.state.showVideo
           ? <video controls ref={(n) => {this._video = n;}} style={vidStyle}>
             <source src={`/system_media/${video.path}`} />
             {video.has_captions
              ? <track kind="subtitles"
                       src={`/api/subtitles?dataset=${DATASET}&video=${encodeURIComponent(video.path)}`}
                       srclang="en" />
              : <span />}
           </video>
           : <div />}
          {this.state.loadingVideo
           ? <div className='loading-video'><img className='spinner' /></div>
           : <div />}
          <FrameView
            bboxes={clip.objects}
            small_width={small_width}
            small_height={small_height}
            full_width={video.width}
            full_height={video.height}
            onClick={this.props.onBoxClick}
            expand={this.state.expand}
            onChangeGender={() => {}}
            onChangeLabel={() => {}}
            onTrack={() => {}}
            onSetTrack={() => {}}
            onDeleteTrack={() => {}}
            onSelect={() => {}}
            path={path} />
        </div>
        {this.state.expand || DISPLAY_OPTIONS.get('show_inline_metadata')
         ?
         <table className='search-result-meta' style={{width: small_width}}>
           <tbody>
             {_.range(Math.ceil(meta.length/meta_per_row)).map((i) =>
               <tr key={i}>
                 {_.range(meta_per_row).map((j) => {
                    let entry = meta[i*meta_per_row + j];
                    if (entry === undefined) { return <td key={j} />; }
                    return (<td key={j} style={td_style}><strong>{entry[0]}</strong>: {entry[1]}</td>);
                 })}
               </tr>)}
           </tbody>
         </table>
         : <div />}
      </div>
    );
  }
}

@observer
class OptionsView extends React.Component {
  fields = [
    {
      name: 'Results per page',
      key: 'results_per_page',
      type: 'number',
      opts: {
        min: 1,
        max: 500
      }
    },
    {
      name: 'Playback speed',
      key: 'playback_speed',
      type: 'range',
      opts: {
        min: 0,
        max: 3,
        step: 0.1
      },
    },
    {
      name: 'Annotation opacity',
      key: 'annotation_opacity',
      type: 'range',
      opts: {
        min: 0,
        max: 1,
        step: 0.1
      },
    },
    {
      name: 'Thumbnail size',
      key: 'thumbnail_size',
      type: 'range',
      opts: {
        min: 1,
        max: 3,
        step: 1
      },
    },
    {
      name: 'Crop bboxes',
      key: 'crop_bboxes',
      type: 'radio'
    },
    {
      name: 'Show gender as border',
      key: 'show_gender_as_border',
      type: 'radio'
    },
    {
      name: 'Show inline metadata',
      key: 'show_inline_metadata',
      type: 'radio'
    },
    {
      name: 'Show hands',
      key: 'show_hands',
      type: 'radio',
    },
    {
      name: 'Show pose',
      key: 'show_pose',
      type: 'radio',
    },
    {
      name: 'Show face',
      key: 'show_face',
      type: 'radio',
    },
    {
      name: 'Show left/right (blue/red)',
      key: 'show_lr',
      type: 'radio'
    },
  ]

  render() {
    return <div className='options'>
      <h2>Options</h2>
      <form>
        {this.fields.map((field, i) =>
           <Rb.FormGroup key={i}>
             <Rb.ControlLabel>{field.name}</Rb.ControlLabel>
             {{
                range: () => (
                  <span>
                    <input type="range" min={field.opts.min} max={field.opts.max}
                           step={field.opts.step} defaultValue={DISPLAY_OPTIONS.get(field.key)}
                           onChange={(e) => {DISPLAY_OPTIONS.set(field.key, e.target.value)}} />
                    {DISPLAY_OPTIONS[field.key]}
                  </span>),
                number: () => (
                  <Rb.FormControl type="number" min={field.opts.min} max={field.opts.max}
                         defaultValue={DISPLAY_OPTIONS.get(field.key)}
                         onKeyPress={(e) => {if (e.key === 'Enter') {
                             DISPLAY_OPTIONS.set(field.key, e.target.value); e.preventDefault();
                           }}} />),
                radio: () => (
                  <Rb.ButtonToolbar>
                    <Rb.ToggleButtonGroup type="radio" name={field.key} defaultValue={DISPLAY_OPTIONS.get(field.key)}
                                          onChange={(e) => {DISPLAY_OPTIONS.set(field.key, e)}}>
                      <Rb.ToggleButton value={true}>Yes</Rb.ToggleButton>
                      <Rb.ToggleButton value={false}>No</Rb.ToggleButton>
                    </Rb.ToggleButtonGroup>
                  </Rb.ButtonToolbar>)
             }[field.type]()}
           </Rb.FormGroup>
        )}
      </form>
    </div>;
  }
}

@observer
class MetadataView extends React.Component {
  render() {
    (window.search_result.result); // ensure that we re-render when search result changes
    let view_keys = [
      ['f', 'expand thumbnail'],
      ['p', 'play clip'],
      ['l', 'play clip in loop']
    ];
    let label_keys = [
      ['click/drag', 'create bounding box'],
      ['d', 'delete bounding box'],
      ['g', 'cycle gender'],
      ['b', 'mark as background face'],
      ['s', 'select frames to save'],
      ['a', 'mark selected as labeled'],
      ['x', 'mark frame to ignore']
      /* ['t', 'start track'],
       * ['q', 'add to track'],
       * ['u', 'delete track']*/
    ];
    return <div className='metadata'>
      <h2>Metadata</h2>
      <div className='meta-block'>
        <div className='meta-key'>Type</div>
        <div className='meta-val'>{window.search_result.type}</div>
      </div>
      <div className='meta-block colors'>
        <div className='meta-key'>Labelers</div>
        <div className='meta-val'>
          {_.values(window.search_result.labelers).map((labeler, i) =>
            <div key={i}>
              {labeler.name}: &nbsp;
              <div style={{backgroundColor: window.search_result.labeler_colors[labeler.id],
                           width: '10px', height: '10px', display: 'inline-box'}} />
            </div>
          )}
          <div className='clearfix' />
        </div>
      </div>
      <div className='meta-block'>
        <div className='meta-key'>Count</div>
        <div className='meta-val'>{window.search_result.count}</div>
      </div>
      <h3>Help</h3>
      <div className='help'>
        On hover over a clip:
        <div>
          <strong>Viewing</strong>
          {view_keys.map((entry, i) =>
            <div key={i}><code>{entry[0]}</code> - {entry[1]}</div>)}
        </div>
        <div>
          <strong>Labeling</strong>
          {label_keys.map((entry, i) =>
            <div key={i}><code>{entry[0]}</code> - {entry[1]}</div>)}
        </div>
      </div>
    </div>;
  }
}

@observer
export default class SearchResultView extends React.Component {
  render() {
    return (
      <div className='search-results'>
        <div className='sidebar left'>
          <MetadataView />
        </div>
        <div className='sidebar right'>
          <OptionsView />
        </div>
        <GroupsView />
      </div>
    )
  }
}
