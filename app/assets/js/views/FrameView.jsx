
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
    document.addEventListener('keypress', this._onKeyPress);
  }

  _onMouseOut = (e) => {
    document.removeEventListener('keypress', this._onKeyPress);
  }

  _onKeyPress = (e) => {
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
    } else if (chr == 'd') {
      this.props.onDelete(this.props.i);
    } else if(chr == 't') {
      this.props.onTrack(this.props.i);
    } else if(chr == 'q') {
      this.props.onSetTrack(this.props.i);
    } else if(chr == 'u') {
      this.props.onDeleteTrack(this.props.i);
    }
  }

  componentDidMount() {
    document.addEventListener('mousemove', this._onMouseMove);
  }

  componentWillUnmount() {
    document.removeEventListener('keypress', this._onKeyPress);
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
      left: box.bbox_x1 * this.props.width + offsetX,
      top: box.bbox_y1 * this.props.height + offsetY,
      width: (box.bbox_x2-box.bbox_x1) * this.props.width,
      height: (box.bbox_y2-box.bbox_y1) * this.props.height,
      borderColor: window.search_result.labeler_colors[box.labeler],
      opacity: window.OPTIONS.annotation_opacity
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

let POSE_PAIRS = [[1,2], [1,5], [2,3], [3,4], [5,6], [6,7], [1,8], [8,9], [9,10],  [1,11],  [11,12], [12,13],  [1,0], [0,14], [14,16],  [0,15], [15,17]];

let POSE_LEFT = [2, 3, 4, 8, 9, 10, 14, 16];

let FACE_PAIRS = [
  [0,1], [1,2], [2,3], [3,4], [4,5], [5,6], [6,7], [7,8], [8,9], [9,10], [10,11], [11,12], [12,13], [13,14], [14,15], [15,16], [17,18], [18,19], [19,20], [20,21], [22,23], [23,24], [24,25], [25,26], [27,28], [28,29], [29,30], [31,32], [32,33], [33,34], [34,35], [36,37], [37,38], [38,39], [39,40], [40,41], [41,36], [42,43], [43,44], [44,45], [45,46], [46,47], [47,42], [48,49], [49,50], [50,51], [51,52], [52,53], [53,54], [54,55], [55,56], [56,57], [57,58], [58,59], [59,48], [60,61], [61,62], [62,63], [63,64], [64,65], [65,66], [66,67], [67,60]];

let HAND_PAIRS = [
  [0,1], [1,2], [2,3], [3,4], [0,5], [5,6], [6,7], [7,8], [0,9], [9,10], [10,11], [11,12], [0,13], [13,14], [14,15], [15,16], [0,17], [17,18], [18,19], [19,20]
];

let POSE_COLOR = 'rgb(255, 60, 60)';
let POSE_LEFT_COLOR = 'rgb(23, 166, 250)';
let FACE_COLOR = 'rgb(240, 240, 240)';
let HAND_LEFT_COLOR = 'rgb(233, 255, 49)';
let HAND_RIGHT_COLOR = 'rgb(95, 231, 118)';

@observer
class PoseView extends React.Component {
  render() {
    let w = this.props.width;
    let h = this.props.height;
    let all_kp = this.props.pose.keypoints;
    let opacity = window.OPTIONS.annotation_opacity;
    let kp_sets = [];

    // Conditionally draw each part of the keypoints depending on our options
    if (window.OPTIONS.show_pose) {
      kp_sets.push([all_kp.pose, POSE_PAIRS, POSE_COLOR]);
    }
    if (window.OPTIONS.show_face) {
      kp_sets.push([all_kp.face, FACE_PAIRS, FACE_COLOR]);
    }
    if (window.OPTIONS.show_hands) {
      kp_sets = kp_sets.concat([
        [all_kp.hand_left, HAND_PAIRS, HAND_LEFT_COLOR],
        [all_kp.hand_right, HAND_PAIRS, HAND_RIGHT_COLOR],
      ])
    }

    let expand = this.props.expand;
    let strokeWidth = this.props.expand ? 3 : 1;

    let get_color = (kp_set, pair) => {
      let color = kp_set[2];
      // Normally color is just the one in the kp_set, but we special case drawing
      // the left side of the pose a different color if the option is enabled
      if (window.OPTIONS.show_lr &&
          kp_set[0].length == all_kp.pose.length &&
          (_.includes(POSE_LEFT, pair[0]) || _.includes(POSE_LEFT, pair[1]))) {
        color = POSE_LEFT_COLOR;
      }
      return color;
    };

    return <svg className='pose'>
      {kp_sets.map((kp_set, j) =>
        <g key={j}>
          {expand
           ? kp_set[0].map((kp, i) => [kp, i]).filter((kptup) => kptup[0][2] > 0).map((kptup, i) =>
             <circle key={i} r={2} cx={kptup[0][0] * w} cy={kptup[0][1] * h}
                     stroke={get_color(kp_set, [kptup[1], kptup[1]])}
                     strokeOpacity={opacity} strokeWidth={strokeWidth} fill="transparent" />
           )
           : <g />}
          {kp_set[1].filter((pair) => kp_set[0][pair[0]][2] > 0 && kp_set[0][pair[1]][2] > 0).map((pair, i) =>
            <line key={i} x1={kp_set[0][pair[0]][0] * w} x2={kp_set[0][pair[1]][0] * w}
                  y1={kp_set[0][pair[0]][1] * h} y2={kp_set[0][pair[1]][1] * h}
                  strokeWidth={strokeWidth} stroke={get_color(kp_set, pair)}
                  strokeOpacity={opacity} />
          )}
        </g>
      )}
    </svg>;
  }
}

// ProgressiveImage displays a loading gif (the spinner) while an image is loading.
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

  _onError = () => {
    // TODO(wcrichto): handle 404 on image (theoretically shouldn't happen, but...)
  }

  componentWillReceiveProps(props) {
    if (this.props.src != props.src) {
      this.setState({loaded: false});
    }
  }

  render() {
    let imgStyle = {display: this.state.loaded ? 'inline-block' : 'none'};
    return (
      <div>
        {this.state.loaded
         ? <div />
         : <img className='spinner' />}
        <img {...this.props} onLoad={this._onLoad} onError={this._onError} style={imgStyle}  />
      </div>
    );
  }
}

// TODO(wcrichto): can we link these with the equivalent values in the CSS?
let SMALL_WIDTH = 100;
let FULL_WIDTH = 780;

export class FrameView extends React.Component {
  state = {
    startX: -1,
    startY: -1,
    curX: -1,
    curY: -1,
    expand: false,
    mouseIn: false,
    imageLoaded: false
  }

  constructor(props) {
    super(props);
  }

  _onMouseOver = (e) => {
    document.addEventListener('mousemove', this._onMouseMove);
    document.addEventListener('keypress', this._onKeyPress);
    if (!(e.buttons & 1)){
      this.setState({startX: -1});
    }
  }

  _onMouseOut = (e) => {
    document.removeEventListener('mousemove', this._onMouseMove);
    document.removeEventListener('keypress', this._onKeyPress);
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

  _onKeyPress = (e) => {
    let chr = String.fromCharCode(e.which);
    if (chr == 's') {
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
      width: this.props.expand ? FULL_WIDTH : (this.props.width * (SMALL_WIDTH / this.props.height)),
      height: this.props.expand ? (this.props.height * (FULL_WIDTH / this.props.width)) : SMALL_WIDTH
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

  componentWillReceiveProps(props) {
    if (this.props.path != props.path) {
      this.setState({imageLoaded: false});
    }
  }

  componentWillUnmount() {
    document.removeEventListener('mousemove', this._onMouseMove);
    document.removeEventListener('keypress', this._onKeyPress);
  }

  render() {
    let imgStyle = this.props.expand ? {width: `${FULL_WIDTH}px`, height: 'auto'} : {};
    let {width, height} = this._getDimensions();
    return (
      <div className='frame'
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
        {this.props.bboxes.map((box, i) => {
          if (box.type == 'bbox') {
            return <BoxView box={box} key={i} i={i} width={width} height={height}
                            onClick={this.props.onClick}
                            onDelete={this._onDelete}
                            onChange={this._onChange}
                            onTrack={this._onTrack}
                            onSetTrack={this._onSetTrack}
                            onDeleteTrack={this._onDeleteTrack}/>;
          } else if (box.type == 'pose') {
            return <PoseView pose={box} key={i} width={width} height={height} expand={this.props.expand} />;
          }})}
         </div>
         : <div />}
        <ProgressiveImage
            src={this.props.path}
            draggable={false}
            style={imgStyle}
            onLoad={() => this.setState({imageLoaded: true})} />
      </div>
    );
  }
};
