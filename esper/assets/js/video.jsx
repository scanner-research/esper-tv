import React from 'react';

export default class Video extends React.Component {
  componentDidMount() {
    this._draw();
  }

  _draw() {
    let frame = Math.round(this._video.currentTime * 24);
    let ctx = this._canvas.getContext('2d');
    let rects = [];
    ctx.clearRect(0, 0, this._canvas.width, this._canvas.height);
    rects.forEach((rect) => {
      ctx.beginPath();
      ctx.lineWidth = '3';
      ctx.strokeStyle = 'red';
      ctx.rect(x, y, w, h);
      ctx.stroke();
    });
    requestAnimationFrame(this._draw.bind(this));
  }

  render() {
    let parts = this.props.path.split('/');
    let basename = parts[parts.length - 1];
    return (
      <div className='video'>
        <div>{basename}</div>
        <div>
          <canvas ref={(n) => { this._canvas = n; }}></canvas>
          <video controls ref={(n) => { this._video = n; }}>
            <source src={"/fs" + this.props.path} />
          </video>
        </div>
      </div>
    );
  }
};
