import React from 'react';
import videojs from 'video.js';
import 'videojs-markers';
import Consumer from 'utils/Consumer.jsx';
import {SearchContext} from './contexts.jsx';

export default class VideoPlayer extends React.Component {
  _lastDisplayTime = -1

  componentDidMount() {
    this._player = videojs(this._videoNode, {
      width: this.props.width,
      height: this.props.height,
      playbackRate: this.props.playbackRate
    });

    let delegate = (k, f) => {
      if (f) {
        this._player.on(k, (e) => f(e, this._player));
      }
    }

    delegate('loadeddata', this.props.onLoadedData);
    delegate('seeked', this.props.onSeeked);
    delegate('texttrackchange', this.props.onTextTrackChange);
    delegate('timeupdate', this.props.onTimeUpdate);

    this._player.on('timeupdate', this._onTimeUpdate);

    let track = this.props.track;
    if (track) {
      this._player.currentTime(this._toSeconds(track.min_frame));

      if (track.max_frame) {
        this._player.markers({
          markerStyle: {
            'width':'8px',
            'background-color': 'red'
          },
          markers: [
            {time: this._toSeconds(track.min_frame), text: "start"},
            {time: this._toSeconds(track.max_frame), text: "end"}
          ]
        });
      }
    }
  }

  _onTimeUpdate = () => {
    // Wrap around if playing in a loop
    if (this.props.loop &&
        this.props.track.max_frame !== undefined &&
        this._player.currentTime() >= this._toSeconds(this.props.track.max_frame)) {
      this._player.currentTime(this._toSeconds(this.props.track.min_frame));
    }
  }

  _toSeconds = (frame) => {
    return frame / this._searchResult.videos[this.props.track.video].fps;
  }

  componentDidUpdate() {
    let checkSet = (k) => {
      if (this.props[k] && this.props[k] != this._player[k]()) {
        this._player[k](this.props[k]);
      }
    };

    checkSet('width');
    checkSet('height');
    checkSet('playbackRate');

    if (this.props.displayTime && this._lastDisplayTime != this.props.displayTime) {
      this._player.currentTime(this.props.displayTime);
      this._lastDisplayTime = this.props.displayTime;
    }

  }

  componentWillUnmount() {
    if (this._player) {
      // wcrichto 6-2-18: DO NOT call dispose like the tutorial says you should. React will get angry.
      // this._player.dispose();
    }
  }

  render() {
    return (
      <Consumer contexts={[SearchContext]}>{searchResult => {
          this._searchResult = searchResult;
          return <div data-vjs-player>
            <video preload='auto' autoPlay controls ref={n => this._videoNode = n} className='video-js'>
              <source src={this.props.video} />
              {this.props.captions
               ? <track kind='captions' src={this.props.captions} srcLang='en' label='English' default />
               : null}
            </video>
          </div>;
      }}</Consumer>
    );
  }
};
