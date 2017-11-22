import React from 'react';
import * as Rb from 'react-bootstrap';
import {observer} from 'mobx-react';
import {observable} from 'mobx';
import {Box, FrameView} from './FrameView.jsx';

class DisplayOptions {
  @observable results_per_page = 50;
  @observable annotation_opacity = 1.0;
  @observable show_pose = true;
  @observable show_face = true;
  @observable show_hands = true;
  @observable show_lr = false;
  @observable crop_bboxes = false;
}

window.DISPLAY_OPTIONS = new DisplayOptions;

@observer
class GroupsView extends React.Component {
  state = {
    page: 0
  }

  _numPages = () => {
    return Math.floor((window.search_result.result.length - 1)/ DISPLAY_OPTIONS.results_per_page);
  }

  _prevPage = (e) => {
    e.preventDefault();
    this.setState({page: Math.max(this.state.page - 1, 0)});
  }

  _nextPage = (e) => {
    e.preventDefault();
    this.setState({page: Math.min(this.state.page + 1, this._numPages())});
  }

  render () {
    return (
      <div className='groups'>
        <div>
          {_.range(DISPLAY_OPTIONS.results_per_page * this.state.page,
                   Math.min(DISPLAY_OPTIONS.results_per_page * (this.state.page + 1),
                            window.search_result.result.length))
            .map((i) => <GroupView key={i} group={window.search_result.result[i]} />)}
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
      <div className={'group ' + group.type}>
        <div>
          <div className='group-label'>{group.label}</div>
          <div className='group-elements'>
            {group.elements.map((clip, i) => <ClipView key={i} clip={clip} />)}
            <div className='clearfix' />
          </div>
        </div>
      </div>
    );
  }
}


class ClipView extends React.Component {
  state = {
    hover: false,
    showVideo: false,
    loadingVideo: false,
    expand: false,
    loopVideo: false
  }

  fullScreen = false

  constructor() {
    super();
    document.addEventListener('webkitfullscreenchange', this._onFullScreen);
    this._timer = null;
  }

  _onFullScreen = () => {
    this.fullScreen = !this.fullScreen;

    if (this.fullScreen && this.state.showVideo) {
      this._video.currentTime = this._toSeconds(this._frameMeta('start').number);
      this._video.pause();
      setTimeout(() => {
        if (this._video) {
          this._video.play();
        }
      }, 1000);
    }
  }

  _onKeyPress = (e) => {
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
    }
  }

  _onMouseEnter = () => {
    document.addEventListener('keypress', this._onKeyPress);
    this.setState({hover: true});
  }

  _onMouseLeave = () => {
    document.removeEventListener('keypress', this._onKeyPress);

    if (this._video) {
      this._video.removeEventListener('seeked', this._onSeeked);
      this._video.removeEventListener('loadeddata', this._onLoadedData);
      this._video.removeEventListener('timeupdate', this._onTimeUpdate);
    }

    if (this._timer) {
      clearTimeout(this._timer);
      this._timer = null;
    }

    this.setState({hover: false, showVideo: false, loadingVideo: false});
  }

  _onClick = () => {
    console.log('Clicked SearchResultView', this.props.clip.objects[0].id);
  }

  _toSeconds = (frame) => {
    return frame / this._videoMeta().fps;
  }

  _onSeeked = () => {
    this.setState({showVideo: true, loadingVideo: false});
  }

  _onLoadedData = () => {
    this._video.currentTime = this._toSeconds(this._frameMeta('start').number);
  }

  _onTimeUpdate = () => {
    if (this.state.loopVideo &&
        this._frameMeta('end') !== undefined &&
        this._video.currentTime >= this._toSeconds(this._frameMeta('end').number)) {
      this._video.currentTime = this._toSeconds(this._frameMeta('start').number);
    }
  }

  componentDidUpdate() {
    if (this._video != null) {
      this._video.addEventListener('seeked', this._onSeeked);
      this._video.addEventListener('loadeddata', this._onLoadedData);
      this._video.addEventListener('timeupdate', this._onTimeUpdate);
    }
  }

  _videoMeta = () => {
    return window.search_result.videos[this.props.clip.video];
  }

  _frameMeta = (ty) => {
    return window.search_result.frames[this.props.clip[ty + '_frame']]
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
    let vidStyle = this.state.showVideo ? {'zIndex': 2} : {};
    let video = this._videoMeta();
    let frame = this._frameMeta('start');
    let path = `/server_media/thumbnails/${window.search_result.dataset}/frame_${clip.start_frame}.jpg`;

    let img_width = this.state.expand ? '780px' : (video.width * (100 / video.height));
    let meta = [];

    if (this.state.expand) {
      meta.push(['Video', `${video.path.split(/[\\/]/).pop()} (${video.id})`]);
      meta.push(['Frame', `${frame.number} (${frame.id})`]);
    }

    if (clip.end_frame !== undefined) {
      let duration = (clip.end_frame - clip.start_frame) / video.fps;
      meta.push(['Duration', `${duration.toFixed(1)}s`]);
    }

    meta.push(['# objects', `${clip.objects.length}`]);

    let meta_per_row = this.state.expand ? 4 : 2;
    let td_style = {width: `${100 / meta_per_row}%`};

    return (
      <div className={'search-result ' + (this.state.expand ? 'expanded' : '')}
           onMouseEnter={this._onMouseEnter}
           onMouseLeave={this._onMouseLeave}
           onClick={this._onClick}>
        <div className='media-container'>
          {this.state.loadingVideo || this.state.showVideo
           ? <video autoPlay controls muted ref={(n) => {this._video = n;}} style={vidStyle}>
             <source src={`/system_media/${video.path}`} />
           </video>
           : <div />}
          {this.state.loadingVideo
           ? <div className='loading-video'><img className='spinner' /></div>
           : <div />}
          <FrameView
            bboxes={clip.objects}
            width={video.width}
            height={video.height}
            onClick={this.props.onBoxClick}
            expand={this.state.expand}
            path={path} />
        </div>
        <table className='search-result-meta' style={{width: img_width}}>
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
      </div>
    );
  }
}

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
    {
      name: 'Crop bboxes',
      key: 'crop_bboxes',
      type: 'radio'
    }
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
                  <input type="range" min={field.opts.min} max={field.opts.max}
                         step={field.opts.step} defaultValue={DISPLAY_OPTIONS[field.key]}
                         onChange={(e) => {DISPLAY_OPTIONS[field.key] = e.target.value}} />),
                number: () => (
                  <Rb.FormControl type="number" min={field.opts.min} max={field.opts.max}
                         defaultValue={DISPLAY_OPTIONS[field.key]}
                         onKeyPress={(e) => {if (e.key === 'Enter') {
                             DISPLAY_OPTIONS[field.key] = e.target.value; e.preventDefault();
                           }}} />),
                radio: () => (
                  <Rb.ButtonToolbar>
                    <Rb.ToggleButtonGroup type="radio" name={field.key} defaultValue={DISPLAY_OPTIONS[field.key]}
                                          onChange={(e) => {DISPLAY_OPTIONS[field.key] = e}}>
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
