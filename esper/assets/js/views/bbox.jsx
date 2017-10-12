import React from 'react';
import {observer} from 'mobx-react';
import {observable, autorun} from 'mobx';
import {Face} from 'models/mod.jsx';

export let boundingRect = (div) => {
  let r = div.getBoundingClientRect();
  return {
    left: r.left + document.body.scrollLeft,
    top: r.top + document.body.scrollTop,
    width: r.width,
    height: r.height
  };
};

// TODO(wcrichto): if you move a box and mouseup outsie the box, then the mouseup doesn't
// register with the BoxView

@observer
class BoxView extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      clickX: -1,
      clickY: -1,
      clicked: false,
      mouseX: -1,
      mouseY: -1
    };
  }

  // See "Bind functions early" https://mobx.js.org/best/react-performance.html
  // for why we use this syntax for member functions.
  _onMouseDown = (e) => {
    this.setState({
      clicked: true,
      clickX: e.pageX,
      clickY: e.pageY,
      mouseX: e.pageX,
      mouseY: e.pageY
    });
    if (this.props.onClick) {
      this.props.onClick(this.props.box);
    }
    e.stopPropagation();
  }

  _onMouseMove = (e) => {
    if (!this.state.clicked) { return; }
    this.setState({
      mouseX: e.pageX,
      mouseY: e.pageY
    });
  }

  _onMouseUp = (e) => {
    let box = this.props.box;
    let {width, height} = this.props;
    let offsetX = this.state.mouseX - this.state.clickX;
    let offsetY = this.state.mouseY - this.state.clickY;
    box.x1 += offsetX / width;
    box.x2 += offsetX / width;
    box.y1 += offsetY / height;
    box.y2 += offsetY / height;
    this.setState({clicked: false});
    e.stopPropagation();
  }

  _onMouseOver = (e) => {
    document.addEventListener('keydown', this._onKeyDown);
  }

  _onMouseOut = (e) => {
    document.removeEventListener('keydown', this._onKeyDown);
  }

  _onKeyDown = (e) => {
    let chr = String.fromCharCode(e.which);
    let box = this.props.box;
    let {width, height} = this.props;
    if (chr == ' ') {
      let cls = 'F';
      if (box.cls == 'F') {
        cls = 'M';
      }
      box.cls = cls;
      this.props.onChange(this.props.i);

      e.preventDefault();
    } else if (chr == 'D') {
      this.props.onDelete(this.props.i);
    } else if(chr == 'T') {
      this.props.onTrack(this.props.i);
    } else if(chr == 'Q') {
      this.props.onSetTrack(this.props.i);
    } else if(chr == 'U') {
      this.props.onDeleteTrack(this.props.i);
    }
  }

  componentDidMount() {
    document.addEventListener('mousemove', this._onMouseMove);
  }

  componentWillUnmount() {
    document.removeEventListener('keydown', this._onKeyDown);
    document.removeEventListener('mousemove', this._onMouseMove);
  }

  render() {
    let box = this.props.box;
    let offsetX = 0;
    let offsetY = 0;
    if (this.state.clicked) {
      offsetX = this.state.mouseX - this.state.clickX;
      offsetY = this.state.mouseY - this.state.clickY;
    }
    let style = {
      left: box.x1 * this.props.width + offsetX,
      top: box.y1 * this.props.height + offsetY,
      width: (box.x2-box.x1) * this.props.width,
      height: (box.y2-box.y1) * this.props.height,
      borderColor: window.COLORS[box.labeler]
    };

    return <div onMouseOver={this._onMouseOver}
                onMouseOut={this._onMouseOut}
                onMouseUp={this._onMouseUp}
                onMouseDown={this._onMouseDown}
                className={`bounding-box gender-${box.cls}`}
                style={style}
                ref={(n) => {this._div = n}} />;
  }
}

class ProgressiveImage extends React.Component {
  state = {
    loaded: false
  }

  _onLoad = () => {
    this.setState({loaded: true});
    if (this.props.onLoad) {
      this.props.onLoad();
    }
  }

  render() {
    return (
      <div>
        {this.state.loaded
         ? <div />
         : <img src='/static/images/spinner.gif' />}
        <img {...this.props} onLoad={this._onLoad} />
      </div>
    );
  }
}

export class BoundingBoxView extends React.Component {
  state = {
    startX: -1,
    startY: -1,
    curX: -1,
    curY: -1,
    fullwidth: false,
    mouseIn: false,
    imageLoaded: false
  }

  constructor(props) {
    super(props);
  }

  _onMouseOver = (e) => {
    document.addEventListener('mousemove', this._onMouseMove);
    document.addEventListener('keydown', this._onKeyDown);
    if (!(e.buttons & 1)){
      this.setState({startX: -1});
    }
  }

  _onMouseOut = (e) => {
    document.removeEventListener('mousemove', this._onMouseMove);
    document.removeEventListener('keydown', this._onKeyDown);
  }

  _onMouseDown = (e) => {
    let rect = boundingRect(this._div);
    this.setState({
      startX: e.pageX - rect.left,
      startY: e.pageY - rect.top
    });
  }

  _onMouseMove = (e) => {
    let rect = boundingRect(this._div);
    let curX = e.pageX - rect.left;
    let curY = e.pageY - rect.top;
    if (0 <= curX && curX <= rect.width &&
        0 <= curY && curY <= rect.height) {
      this.setState({curX: curX, curY: curY});
    }
  }

  _onMouseUp = (e) => {
    this.props.bboxes.push(this._makeBox());
    this.setState({startX: -1});
  }

  _onKeyDown = (e) => {
    let chr = String.fromCharCode(e.which);
    if (chr == 'F') {
      this.setState({fullwidth: !this.state.fullwidth});
    } else if (chr == 'S') {
      this.props.onSelect(this.props.ni);
    }
  }

  _onDelete = (i) => {
    this.props.bboxes.splice(i, 1);
  }

  _onChange = (i) => {
    let box = this.props.bboxes[i];
    this.props.onChange(box);
  }

  _onTrack = (i) => {
    let box = this.props.bboxes[i];
    this.props.onTrack(box);
  }

  _onSetTrack = (i) => {
    let box = this.props.bboxes[i];
    this.props.onSetTrack(box);
  }

  _onDeleteTrack = (i) => {
    let box = this.props.bboxes[i];
    this.props.onDeleteTrack(box);
  }

  _getDimensions() {
    return {
      width: this.state.fullwidth ? 780 : (this.props.width * (100 / this.props.height)),
      height: this.state.fullwidth ? (this.props.height * (780 / this.props.width)) : 100
    };
  }

  _makeBox() {
    let {width, height} = this._getDimensions();
    return new Face({
       bbox: {
         x1: this.state.startX/width,
         y1: this.state.startY/height,
         x2: this.state.curX/width,
         y2: this.state.curY/height,
         labeler: 'handlabeled'
       },
       track: null,
       gender: '0'
    });
  }

  render() {
    let imgStyle = this.state.fullwidth ? {width: '780px', height: 'auto'} : {};
    let {width, height} = this._getDimensions();
    return (
      <div className='bounding-boxes'
           onMouseDown={this._onMouseDown}
           onMouseUp={this._onMouseUp}
           onMouseOver={this._onMouseOver}
           onMouseOut={this._onMouseOut}
           ref={(n) => { this._div = n; }}>
        {this.state.imageLoaded
         ? <div>
        {this.state.startX != -1
         ? <BoxView box={this._makeBox()} width={width} height={height} />
         : <div />}
        {this.props.bboxes.map((box, i) =>
          <BoxView box={box} key={i} i={i} width={width} height={height}
                   onClick={this.props.onClick}
                   onDelete={this._onDelete}
                   onChange={this._onChange}
                   onTrack={this._onTrack}
                   onSetTrack={this._onSetTrack}
                   onDeleteTrack={this._onDeleteTrack}/>)}
         </div>
         : <div />}
        <ProgressiveImage src={this.props.path} draggable={false} style={imgStyle} onLoad={() => this.setState({imageLoaded: true})} />
      </div>
    );
  }
};
