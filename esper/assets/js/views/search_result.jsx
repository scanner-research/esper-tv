import React from 'react';
import {Box, BoundingBoxView} from './bbox.jsx';

export default class SearchResultView extends React.Component {
  state = {
    hover: false,
    showVideo: false
  }

  _onMouseEnter() {
    this.setState({hover: true, showVideo: false});
  }

  _onMouseLeave() {
    this._video.removeEventListener('seeked', this._onSeeked);
    this._video.removeEventListener('loadeddata', this._onLoadedData);
    this._video.removeEventListener('timeupdate', this._onTimeUpdate);
    this.setState({hover: false, showVideo: false});
  }

  _onClick() {
    console.log('Clicked SearchResultView');
  }

  _toSeconds(frame) {
    return frame / this.props.video.fps;
  }

  _onSeeked = () => {
    this.setState({showVideo: true});
  }

  _onLoadedData = () => {
    if (this.props.clip.start !== undefined) {
      this._video.currentTime = this._toSeconds(this.props.clip.start);
    }
  }

  _onTimeUpdate = () => {
    if (this._video.currentTime >= this._toSeconds(this.props.clip.end)) {
      this._video.currentTime = this._toSeconds(this.props.clip.start);
    }
  }

  componentDidUpdate() {
    if (this._video != null) {
      this._video.addEventListener('seeked', this._onSeeked);
      this._video.addEventListener('loadeddata', this._onLoadedData);
      this._video.addEventListener('timeupdate', this._onTimeUpdate);
    }
  }

  render() {
    let vidStyle = this.state.showVideo ? {'zIndex': 2} : {};
    let path = `/media/assets/thumbnails/frame_${this.props.clip.frame}.jpg`;
    let my_box = <BoundingBoxView
                     bboxes={this.props.clip.bboxes}
                     width={this.props.video.width}
                     height={this.props.video.height}
                     path={path} />;
    let other_box = this.props.clip.other_bboxes
                  ? <BoundingBoxView
                        bboxes={this.props.clip.other_bboxes}
                        width={this.props.video.width}
                        height={this.props.video.height}
                        path={path} />
                  : <div />;
    return (
      <div className='search-result'
           onMouseEnter={this._onMouseEnter.bind(this)}
           onMouseLeave={this._onMouseLeave.bind(this)}
           onClick={this._onClick}>
        {this.state.hover
         ? <video autoPlay muted ref={(n) => {this._video = n;}} style={vidStyle}>
           <source src={`/media/${this.props.video.path}`} />
         </video>
         : <div />}
        {this.props.clip.bboxes.length > 0 && this.props.clip.bboxes[0].labeler == "tinyfaces"
         ? <div>{my_box}{other_box}</div>
         : <div>{other_box}{my_box}</div>}
      </div>
    );
  }
}
