import React from 'react';
import {observer} from 'mobx-react';
import {FrameView} from './FrameView.jsx';
import Spinner from './Spinner.jsx';
import manager from 'utils/KeyboardManager.jsx';
import {FrontendSettingsContext, SearchContext} from './contexts.jsx';
import Consumer from 'utils/Consumer.jsx';
import _ from 'lodash';

@observer
export default class ClipView extends React.Component {
  state = {
    showVideo: false,
    loadingVideo: false,
    loopVideo: false,
    subAutoScroll: true
  }

  fullScreen = false
  frames = []
  _lastDisplayTime = -1
  _formattedSubs = null
  _curSub = null
  _subDivs = null
  _n = null

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
    if (manager.locked()) {
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

  _subDivScroll = (subDiv) => {
    return (subDiv.offsetTop + subDiv.clientHeight / 2) - this._subContainer.clientHeight / 2;
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

      if (this.props.displayTime !== undefined && this._lastDisplayTime != this.props.displayTime) {
        this._video.currentTime = this.props.displayTime;
        this._lastDisplayTime = this.props.displayTime;
      }

      let updateFps = 24;
      if (this._timeUpdateInterval) {
        clearInterval(this._timeUpdateInterval);
      }
      this._timeUpdateInterval = setInterval(() => {
        if (this.props.onTimeUpdate) {
          this.props.onTimeUpdate(this._video.currentTime);
        }

        // HACK FOR NOW: need to forcibly re-render every tick for subtitles to work properly
        this.forceUpdate();
      }, 1000 / updateFps);

      // Scroll captions to current time
      if (this._curSub !== null && this.state.subAutoScroll && this._subContainer !== null) {
        let subDiv = this._subDivs[this._curSub];
        this._subContainer.scrollTop = this._subDivScroll(subDiv);
      }
    } else {
      this._curSub = null;
      this._subDivs = null;

      // If the video disappears after being shown (e.g. b/c the clip was de-expanded)
      // we have to catch the interval clear then too
      if (this._timeUpdateInterval) {
        clearInterval(this._timeUpdateInterval);
      }
    }
  }

  _videoMeta = () => {
    return this._searchResult.videos[this.props.clip.video];
  }

  _subOnScroll = (e) => {
    if (this.state.subAutoScroll) {
      return;
    }

    // TODO: change video time when scrolling
    let scroll = this._subContainer.scrollTop;

    let i;
    for (i = 0; i < _.size(this._subDivs); ++i) {
      if (scroll < this._subDivScroll(this._subDivs[i])) {
        break;
      }
    }

    i = Math.min(i, _.size(this._subDivs) - 1);

    this._video.currentTime = this._formattedSubs[i].start;
  }

  componentWillUnmount() {
    document.removeEventListener('keypress', this._onKeyPress);
    if (this._timeUpdateInterval) {
      clearInterval(this._timeUpdateInterval);
    }
  }

  width() {
    console.assert(this._n !== null);
    return this._n.clientWidth;
  }

  render() {
    return (
      <Consumer contexts={[FrontendSettingsContext, SearchContext]}>{(frontendSettings, searchResult) => {
        this._searchResult = searchResult;
          let clip = this.props.clip;
          let video = this._videoMeta();
          let show_subs = frontendSettings.get('subtitle_sidebar');

          // Set playback rate of the video
          if (this._video) {
            this._video.playbackRate = frontendSettings.get('playback_speed');
          }

          // Figure out how big the thumbnail should be
          let small_height = this.props.expand ? video.height : 100 * frontendSettings.get('thumbnail_size');
          let small_width = video.width * small_height / video.height;
          let vidStyle = this.state.showVideo ? {
            zIndex: 2,
            width: small_width,
            height: small_height
          } : {};

          // Determine which video frame to display
          let display_frame =
            frontendSettings.get('show_middle_frame') && clip.max_frame
            ? Math.round((clip.max_frame + clip.min_frame) / 2)
            : clip.min_frame;
          let path = `${window.location.protocol}//${window.location.hostname}/frameserver/fetch?path=${encodeURIComponent(video.path)}&frame=${display_frame}`;

          // Collect inline metadata to display
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

          let sub_width = this.props.expand ? 480 : 50;
          let subStyle = {
            width: sub_width,
            fontSize: this.props.expand ? '14px' : '12px'
          };

          let SubtitleView = () => {
            if (this._video.textTracks.length == 0) {
              return <span>Loading track...</span>
            }
            let subs = this._video.textTracks[0].cues;
            if (!subs || subs.length == 0) {
              return <span>Loading subtitles...</span>
            }

            // TODO: is there a proper way to cache this? We can't just compute it on the first
            // go since the text tracks are streamed in, not loaded all in at once.
            this._formattedSubs = [];
            let curSub = "";
            let startTime = 0;
            _.forEach(subs, (sub) => {
              let parts = sub.text.split('>>');
              curSub += parts[0] + ' ';

              if (parts.length > 1) {
                this._formattedSubs.push({
                  text: _.trim(curSub),
                  start: startTime,
                  end: sub.endTime
                })

                startTime = sub.startTime;
                parts.slice(1, -1).forEach((text) => {
                  this._formattedSubs.push({
                    text: _.trim(text),
                    start: startTime,
                    end: sub.endTime
                  })
                });

                curSub = parts[parts.length - 1];
              }
            });

            let i = 0;
            while (i < this._formattedSubs.length && this._formattedSubs[i].start <= this._video.currentTime) { i++; }

            this._curSub = Math.max(i - 1, 0);
            this._subDivs = {};
            return <div>{this._formattedSubs.map((sub, j) =>
              <div key={j} className='subtitle' ref={(n) => { this._subDivs[j] = n; }}>
                {this._curSub == j ? <strong>>> {sub.text}</strong> : <span>>> {sub.text}</span>}
              </div>)}
            </div>;
          };

          return <div className={`clip ${(this.props.expand ? 'expanded' : '')}`}
                      onMouseEnter={this._onMouseEnter}
                      onMouseLeave={this._onMouseLeave}
                      ref={(n) => {this._n = n;}}>
            <div className='video-row' style={{height: small_height}}>
              <div className='media-container'>
                {this.state.loadingVideo || this.state.showVideo
                 ? <video controls ref={(n) => {this._video = n;}} style={vidStyle}>
                   <source src={`/system_media/${video.path}`} />
                   {video.srt_extension != ''
                    ? <track kind="subtitles"
                             src={`/api/subtitles?video=${video.id}`}
                             srcLang="en" />
                    : <span />}
                 </video>
                 : <div />}
                {this.state.loadingVideo
                 ? <div className='loading-video'><Spinner /></div>
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
              {show_subs && this.props.expand && this._video
               ? <div className='sub-container' style={subStyle}>
                 <button className='sub-autoscroll' onClick={() => {
                     this.setState({subAutoScroll: !this.state.subAutoScroll});
                 }}>
                   {this.state.subAutoScroll ? 'Disable autoscroll' : 'Enable autoscroll'}
                 </button>
                 <div className='sub-scroll' onScroll={this._subOnScroll}
                      style={{overflow: this.state.subAutoScroll ? 'hidden' : 'auto'}}
                      ref={(n) => {this._subContainer = n;}}>
                   <SubtitleView />
                 </div>
               </div>
               : <div />}
            </div>
            {(this.props.expand || frontendSettings.get('show_inline_metadata')) && this.props.showMeta
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
      }}</Consumer>
    );
  }
}
