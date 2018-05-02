import React from 'react';
import {observer} from 'mobx-react';
import {FrameView} from './FrameView.jsx';

@observer
export default class ClipView extends React.Component {
  state = {
    showVideo: false,
    loadingVideo: false,
    loopVideo: false
  }

  fullScreen = false
  frames = []
  _lastDisplayTime = -1

  constructor() {
    super();
    document.addEventListener('webkitfullscreenchange', this._onFullScreen);
  }

  _onFullScreen = () => {
    this.fullScreen = !this.fullScreen;

    if (this.fullScreen && this.state.showVideo) {
      this._video.currentTime = this._toSeconds(this.props.clip.min_frame);
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
    } else if (chr == ' ') {
      if (this._video) {
        let isPlaying = this._video.currentTime > 0 && !this._video.paused && !this._video.ended;
        if (isPlaying) {
          this._video.pause();
        } else {
          this._video.play();
        }
        e.stopPropagation();
        e.preventDefault();
      }
    }
  }

  _onMouseEnter = () => {
    document.addEventListener('keypress', this._onKeyPress);
  }

  _onMouseLeave = () => {
    document.removeEventListener('keypress', this._onKeyPress);

    if (!this.props.expand) {
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
    this._video.currentTime = this._toSeconds(this.props.clip.min_frame);
    if (this._video.textTracks.length > 0) {
      this._video.textTracks[0].mode = 'showing';
    }
    this._video.play();
  }

  _onTimeUpdate = () => {
    if (this.state.loopVideo &&
        this.props.clip.max_frame !== undefined &&
        this._video.currentTime >= this._toSeconds(this.props.clip.max_frame)) {
      this._video.currentTime = this._toSeconds(this.props.clip.min_frame);
    }
  }

  componentDidUpdate() {
    if (this._video) {
      this._video.addEventListener('seeked', this._onSeeked);
      this._video.addEventListener('loadeddata', this._onLoadedData);
      this._video.addEventListener('timeupdate', this._onTimeUpdate);

      if (this.props.onVideoPlay) {
        this._video.addEventListener('playing', this.props.onVideoPlay);
        this._video.addEventListener('pause', this.props.onVideoStop);
        this._video.addEventListener('ended', this.props.onVideoStop);
      }

      if (this._lastDisplayTime != this.props.displayTime) {
        this._video.currentTime = this.props.displayTime;
        this._lastDisplayTime = this.props.displayTime;
      }

      if (this.props.onTimeUpdate) {
        if (this._timeUpdateInterval) {
          clearInterval(this._timeUpdateInterval);
        }
        this._timeUpdateInterval = setInterval(() => {
          this.props.onTimeUpdate(this._video.currentTime);
        }, 16);
      }
    } else {
      // If the video disappears after being shown (e.g. b/c the clip was de-expanded)
      // we have to catch the interval clear then too
      if (this._timeUpdateInterval) {
        clearInterval(this._timeUpdateInterval);
      }
    }
  }

  _videoMeta = () => {
    return window.search_result.videos[this.props.clip.video];
  }

  componentWillUnmount() {
    document.removeEventListener('keypress', this._onKeyPress);
    if (this._timeUpdateInterval) {
      clearInterval(this._timeUpdateInterval);
    }
  }

  render() {
    let clip = this.props.clip;
    let video = this._videoMeta();

    let meta = [];

    if (this.props.expand) {
      meta.push(['Video', `${video.path.split(/[\\/]/).pop()} (${video.id})`]);
      meta.push(['Frame', `${display_frame}`]);
    }

    if (clip.max_frame !== undefined) {
      let duration = (clip.max_frame - clip.min_frame) / video.fps;
      meta.push(['Duration', `${duration.toFixed(1)}s`]);
    }

    if (clip.objects !== undefined) {
      meta.push(['# objects', `${clip.objects.length}`]);
    }

    if (clip.metadata !== undefined) {
      clip.metadata.forEach((entry) => {
        meta.push([entry[0], entry[1]]);
      });
    }

    let meta_per_row = this.props.expand ? 4 : 2;
    let td_style = {width: `${100 / meta_per_row}%`};

    if (this._video) {
      this._video.playbackRate = DISPLAY_OPTIONS.get('playback_speed');
    }

    let small_height = this.props.expand ? video.height : 100 * DISPLAY_OPTIONS.get('thumbnail_size');
    let small_width = video.width * small_height / video.height;
    let vidStyle = this.state.showVideo ? {
      zIndex: 2,
      width: small_width,
      height: small_height
    } : {};

    let display_frame =
      DISPLAY_OPTIONS.get('show_middle_frame') && clip.max_frame
      ? Math.round((clip.max_frame + clip.min_frame) / 2)
      : clip.min_frame;
    let path = `/frameserver/fetch?path=${encodeURIComponent(video.path)}&frame=${display_frame}&height=${small_height}`;

    return (
      <div className={`clip ${(this.props.expand ? 'expanded' : '')}`}
           onMouseEnter={this._onMouseEnter}
           onMouseLeave={this._onMouseLeave}>
        <div className='media-container'>
          {this.state.loadingVideo || this.state.showVideo
           ? <video controls ref={(n) => {this._video = n;}} style={vidStyle}>
             <source src={`/system_media/${video.path}`} />
             {video.has_captions
              ? <track kind="subtitles"
                       src={`/api/subtitles?dataset=${DATASET}&video=${video.id}`}
                       srclang="en" />
              : <span />}
           </video>
           : <div />}
          {this.state.loadingVideo
           ? <div className='loading-video'><img className='spinner' /></div>
           : <div />}
          <FrameView
            bboxes={clip.objects || []}
            small_width={small_width}
            small_height={small_height}
            full_width={video.width}
            full_height={video.height}
            onClick={this.props.onBoxClick}
            expand={this.props.expand}
            onChangeGender={() => {}}
            onChangeLabel={() => {}}
            onTrack={() => {}}
            onSetTrack={() => {}}
            onDeleteTrack={() => {}}
            onSelect={() => {}}
            path={path} />
        </div>
        {(this.props.expand || DISPLAY_OPTIONS.get('show_inline_metadata')) && this.props.showMeta
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
