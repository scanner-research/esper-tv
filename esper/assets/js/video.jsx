import React from 'react';
import axios from 'axios';

export default class Video extends React.Component {
  constructor(props) {
    super(props);
    this.state = {bboxes: [], show_video: false};
    axios.get('/faces', {
      params: {
        id: this.props.id
      }
    }).then(((response) => {
      this.setState({
        bboxes: response.data.faces
      });
    }).bind(this));
  }

  componentDidMount() {
    this._draw();
  }

  // TODO(wcrichto): bboxes can get off w/ video when skipping around a bunch?
  _draw() {
    if (this._video !== undefined) {
      let frame = Math.round(this._video.currentTime * 24);
      let ctx = this._canvas.getContext('2d');
      ctx.clearRect(0, 0, this._canvas.width, this._canvas.height);
      this.state.bboxes[frame].forEach((bbox) => {
        let x = bbox[0];
        let y = bbox[1];
        let w = bbox[2] - x;
        let h = bbox[3] - y;
        let scale = this._canvas.width / this.props.width;;
        ctx.beginPath();
        ctx.lineWidth = '3';
        ctx.strokeStyle = 'red';
        ctx.rect(x * scale, y * scale, w * scale, h * scale);
        ctx.stroke();
      });
    }
    requestAnimationFrame(this._draw.bind(this));
  }

  _onClickThumbnail() {
    this.setState({show_video: true});
  }

  render() {
    let parts = this.props.path.split('/');
    let basename = parts[parts.length - 1];
    return (
      <div className='video'>
        <div>{basename}</div>
        {!this.state.show_video
        ? (<img src={"/static/thumbnails/" + this.props.id + ".jpg"}
                onClick={this._onClickThumbnail.bind(this)} />)
         : (this.state.bboxes.length == 0
          ? (<div>Loading...</div>)
          : (<div>
            <canvas ref={(n) => { this._canvas = n; }}></canvas>
            <video controls ref={(n) => { this._video = n; }}>
              <source src={"/fs" + this.props.path} />
            </video>
          </div>))}
      </div>
    );
  }
};
