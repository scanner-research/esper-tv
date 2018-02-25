import React from 'react';
import {boundingRect} from './FrameView.jsx';
import ClipView from './ClipView.jsx';
import {observer} from 'mobx-react';

@observer
export default class TimelineView extends React.Component {
  state = {
    currentTime: 0,
    clickedTime: -1,
    displayTime: -1,
    startX: -1,
    startY: -1
  }

  _onTimeUpdate = (t) => {
    this.setState({currentTime: t});
  }

  _localCoords = (e) => {
    let rect = boundingRect(this._svg);
    return [e.clientX - rect.left, e.clientY - rect.top];
  }

  _onMouseDown = (e) => {
    let [x, y] = this._localCoords(e);
    this.setState({startX: x, startY: y, clickedTime: this.state.currentTime});
  }

  _onMouseMove = (e) => {
    if (this.state.startX != -1) {
      let [x, y] = this._localCoords(e);
      let dx = x - this.state.startX;
      let dt = DISPLAY_OPTIONS.get('timeline_range') * dx / boundingRect(this._svg).width * -1;
      this.setState({
        displayTime: this.state.clickedTime + dt,
        currentTime: this.state.clickedTime + dt
      });
    }
  }

  _onMouseUp = (e) => {
    this.setState({startX: -1, startY: -1});
  }

  _onMouseLeave = (e) => {
    if (this.state.startX != -1) {
      this.setState({startX: -1, startY: -1});
    }
  }

  _video = () => {
    return window.search_result.videos[this.props.group.elements[0].video];
  }

  render() {
    let group = this.props.group;
    let expand = this.props.expand;

    let clip = {
      video: group.elements[0].video,
      start_frame: group.elements[0].start_frame,
      end_frame: group.elements[group.elements.length-1].end_frame
    };

    let video = this._video();
    let small_height = expand ? video.height : 100 * DISPLAY_OPTIONS.get('thumbnail_size');
    let small_width = video.width * small_height / video.height;

    let style = {
      width: small_width,
    };

    let timeboxStyle = {
      width: small_width,
      height: expand ? 60 : 20
    }
    let w = timeboxStyle.width;
    let h = timeboxStyle.height;

    let mw = expand ? 4 : 2;
    let mh = timeboxStyle.height;
    let mf = expand ? 16 : 12;

    return (<div className='timeline' style={style}>
      <ClipView clip={clip} group_id={this.props.group_id} onTimeUpdate={this._onTimeUpdate} showMeta={false}
                expand={this.props.expand} displayTime={this.state.displayTime} />
      <svg className='time-container' style={timeboxStyle} onMouseDown={this._onMouseDown}
           onMouseMove={this._onMouseMove}
           onMouseUp={this._onMouseUp}
           onMouseLeave={this._onMouseLeave}
           ref={(n) => {this._svg = n;}}>
        <line x1={w/2} x2={w/2} y1={0} y2={h} stroke="rgb(200, 30, 30)" strokeWidth={mw} />
        <g>
          {group.elements.map(((elt, i) => {
             let label = elt.label;
             let start = elt.start_frame / video.fps;
             let end = elt.end_frame / video.fps;
             return <g key={i}>{[[start, 'open'], [end, 'close']].map((([t, ty], j) => {
                 let x = w/2 + (t - this.state.currentTime) / (DISPLAY_OPTIONS.get('timeline_range')/2) * w/2;
                 if (0 <= x && x <= w) {
                   let margin = mw;
                   if (ty == 'open') {
                     let points = `${mw*2},${margin} 0,${margin} 0,${mh-2*margin} ${mw*2},${mh-2*margin}`;
                     return (<g key={j} transform={`translate(${x}, 0)`}>
                       <polyline fill="none" stroke="black" strokeWidth={mw} points={points} />
                       <text x={mw+4} y={h/2} alignmentBaseline="middle" fontSize={mf}>{label}</text>
                     </g>);
                   } else if (ty == 'close') {
                     let points = `${-mw*2},${margin} 0,${margin} 0,${mh-2*margin} ${-mw*2},${mh-2*margin}`;
                     return (<g key={j} transform={`translate(${x}, 0)`}>
                       <polyline fill="none" stroke="black" strokeWidth={mw} points={points} />
                       <text x={-(mw+4)} y={h/2} alignmentBaseline="middle" textAnchor="end" fontSize={mf}>{label}</text>
                     </g>);
                     return (<div key={j} />);
                   }
                 } else {
                   return (<div key={j} />);
                 }
             }).bind(this))}
             </g>;
          }).bind(this))}
        </g>
      </svg>
    </div>);
  }
}
