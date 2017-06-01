import React from 'react';
import axios from 'axios';
import {Link} from 'react-router-dom';
import {observer} from 'mobx-react';
import {observable, autorun} from 'mobx';

@observer
export default class IdentitySummary extends React.Component {
  constructor(props) {
    super(props);
    this.identity = props.store;
    this._unmounted = false;
  }

  componentDidMount() {
    this._draw();
  }

  componentWillUnmount() {
    this._unmounted = true;
  }

  // Don't think we need this one.
  componentWillReceiveProps(props) {
    {/*if (this._identity !== undefined && props.frame != this._lastUpdatedFrame) {*/}
      {/*this._video.currentTime = props.frame / this.video.fps;*/}
      {/*this._lastUpdatedFrame = props.frame;*/}
    {/*}*/}
  }

  // Relation with render.
  _draw() {
    if (this._unmounted) { return; }
    if (this._video !== undefined) {
      let frame = Math.round(this._video.currentTime * this.video.fps);
      this._canvas.width = this._video.clientWidth;
      this._canvas.height = this._video.clientHeight - 30;
      let ctx = this._canvas.getContext('2d');
      ctx.clearRect(0, 0, this._canvas.width, this._canvas.height);

    }
    requestAnimationFrame(this._draw.bind(this));
  }

  _onClickThumbnail() {
    this.setState({show_video: true});
    this.video.loadFaces();
  }

  // I guess main stuff happens in here.
  render() {
    let video = this.video;
    let parts = video.path.split('/');
    let basename = parts[parts.length - 1];
    return (
      <div className='video-summary'>
        {this.props.show_meta
        ? <div><Link to={'/video/' + video.id}>{basename}</Link></div>
        : <div />}
        {!this.state.show_video
        ? (<img src={"/static/thumbnails/" + video.id + ".jpg"}
                onClick={this._onClickThumbnail.bind(this)} />)
         : (this.video.loadedFaces == 0
          ? (<div>Loading...</div>)
          : (<div>
            <canvas ref={(n) => { this._canvas = n; }}></canvas>
            <video controls ref={(n) => { this._video = n; }}>
              <source src={"/fs/usr/src/app/" + video.path} />
            </video>
          </div>))}
      </div>
    );
  }
};
