import React from 'react';
import {Box, BoundingBoxView} from './bbox.jsx';
import {observer} from 'mobx-react';

class ClipView extends React.Component {
  state = {
    hover: false,
    showVideo: false,
    loadingVideo: false,
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

  _onKeyPress = (e) => {
    let chr = String.fromCharCode(e.which);
    if (chr == 'p') {
      this.setState({
        showVideo: false,
        loadingVideo: true
      });
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

  componentWillUnmount() {
    document.removeEventListener('keypress', this._onKeyPress);
  }

  render() {
    let clip = this.props.clip;
    let vidStyle = this.state.showVideo ? {'zIndex': 2} : {};
    let video = this._videoMeta();
    let frame = this._frameMeta('start');
    let path = `/server_media/thumbnails/tvnews/frame_${clip.start_frame}.jpg`;
    let img_width = video.width * (100 / video.height);
    let meta = [`# people: ${clip.bboxes.length}`];
    if (clip.end_frame !== undefined) {
      let duration = (clip.end_frame - clip.start_frame) / video.fps;
      meta.push(`Duration: ${duration.toFixed(1)}s`);
    }
    /* let path = `https://frameserver-dot-visualdb-1046.appspot.com/?path=${encodeURIComponent(video.path)}&frame=${frame.number}&id=${clip.start_frame}`;*/
    return (
      <div className='search-result'
           onMouseEnter={this._onMouseEnter}
           onMouseLeave={this._onMouseLeave}
            onClick={this._onClick}>
        {this.state.loadingVideo || this.state.showVideo
         ? <video autoPlay controls muted ref={(n) => {this._video = n;}} style={vidStyle}>
           <source src={`/system_media/${video.path}`} />
         </video>
         : <div />}
        {this.state.loadingVideo
         ? <div className='loading-video'><img src="/static/images/spinner.gif" /></div>
         : <div />}
        <BoundingBoxView
          bboxes={clip.bboxes}
          width={video.width}
          height={video.height}
          onClick={this.props.onBoxClick}
          path={path} />
        <table className='search-result-meta' style={{width: img_width}}>
          <tbody>
            {_.range(Math.ceil(meta.length/2)).map((i) =>
            <tr key={i}>
              <td>{meta[i*2]}</td>
              <td>{meta[i*2+1]}</td>
            </tr>)}
          </tbody>
        </table>
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
