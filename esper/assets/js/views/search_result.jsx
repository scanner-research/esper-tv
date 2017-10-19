import React from 'react';
import {Box, BoundingBoxView} from './bbox.jsx';
import {observer} from 'mobx-react';

const HOVER_TO_SHOW_VIDEO_DELAY = 1000;

class ClipView extends React.Component {
  state = {
    hover: false,
    showVideo: false,
    loadingVideo: false,
    hoverLongEnough: false
  }

  fullScreen = false

  constructor() {
    super();
    document.addEventListener('webkitfullscreenchange', this._onFullScreen);
    this._timer = null;
  }

  _onFullScreen = () => {
    this.fullScreen = !this.fullScreen;
  }

  _onMouseEnter = () => {
    this.setState({hover: true, showVideo: false, loadingVideo: true, hoverLongEnough: false});
    this._timer = setTimeout((() => {
      this.setState({hoverLongEnough: true});
    }).bind(this), HOVER_TO_SHOW_VIDEO_DELAY);
  }

  _onMouseLeave = () => {
    if (this._video) {
      this._video.removeEventListener('seeked', this._onSeeked);
      this._video.removeEventListener('loadeddata', this._onLoadedData);
      this._video.removeEventListener('timeupdate', this._onTimeUpdate);
    }

    if (this._timer) {
      clearTimeout(this._timer);
      this._timer = null;
    }

    this.setState({hover: false, showVideo: false, loadingVideo: false, hoverLongEnough: false});
  }

  _onClick = () => {
    console.log('Clicked SearchResultView', this.props.clip.bboxes[0].id);
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
    if (!this.state.fullScreen &&
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

  render() {
    let clip = this.props.clip;
    let vidStyle = this.state.showVideo ? {'zIndex': 2} : {};
    let video = this._videoMeta();
    let frame = this._frameMeta('start');
    let path = `/server_media/thumbnails/tvnews/frame_${clip.start_frame}.jpg`;
    /* let path = `https://frameserver-dot-visualdb-1046.appspot.com/?path=${encodeURIComponent(video.path)}&frame=${frame.number}&id=${clip.start_frame}`;*/
    return (
      <div className='search-result'
           onMouseEnter={this._onMouseEnter}
           onMouseLeave={this._onMouseLeave}
           onClick={this._onClick}>
        {this.state.hover && this.state.hoverLongEnough
         ? <video autoPlay controls muted ref={(n) => {this._video = n;}} style={vidStyle}>
           <source src={`/system_media/${video.path}`} />
         </video>
         : <div />}
        {this.state.hoverLongEnough && this.state.loadingVideo
         ? <div className='loading-video'><img src="/static/images/spinner.gif" /></div>
         : <div />}
        <BoundingBoxView
          bboxes={clip.bboxes}
          width={video.width}
          height={video.height}
          onClick={this.props.onBoxClick}
          path={path} />
      </div>
    );
  }
}

@observer
export default class SearchResultView extends React.Component {
  render() {
    return (
      <div className='search-results'>
        <div className='colors'>
          {_.values(window.search_result.labelers).map((labeler, i) =>
            <div key={i}>
             {labeler.name}: &nbsp;
              <div style={{backgroundColor: window.search_result.labeler_colors[labeler.id],
                           width: '10px', height: '10px', display: 'inline-box'}} />
            </div>
          )}
        </div>
        <div className='clips'>
          {window.search_result.result.map((clip, i) =>
            <ClipView key={i} clip={clip} />
          )}
        </div>
      </div>
    )
  }
}
