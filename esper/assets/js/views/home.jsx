import React from 'react';
import ReactDOM from 'react-dom';
import {observable} from 'mobx';
import {observer} from 'mobx-react';
import axios from 'axios';
import {BoundingBoxView, BoxView} from './bbox.jsx';
import {Form, FormGroup, FormControl, FieldGroup, ControlLabel, InputGroup, Button} from 'react-bootstrap';

class SearchResult {
  @observable clips = {};
  @observable videos = {};
};

// FIXME: this should depend on the detection rate used when ingesting video /
// detecting bboxes ...
let DETECTION_FPS = 24;

class PropertyInput extends React.Component {
  render() {
    if (this.props.type == "string") {
      return <FormControl type="text" />;
    } else if (this.props.type == "enum") {
      return <FormControl componentClass="select" placeholder='Select...'><option>Barack Obama</option><option>Hillary Clinton</option><option>Donald Trump</option></FormControl>;
    } else if (this.props.type == "int") {
      return <FormControl type="number" />;
    } else {
      console.error(`Invalid property type ${this.props.type}`);
    }
  }
};

class SearchInput extends React.Component {
  //  TODO(wcrichto): fetch these automatically from SQL schema
  properties = {
    video: [
      ['id', 'int'],
      ['path', 'string'],
      ['width', 'int'],
      ['height', 'int'],
      ['show', 'enum'],
    ],
    face: [
      ['id', 'int'],
      ['identity', 'enum']
    ],
    face_diffs: [
      ['id', 'int']
    ]
  }

  state = {
    selectedConcept: 'video',
    selectedProperty: null,
    properties: []
  }

  _onSearch(e) {
    e.preventDefault();
    let concept = e.target.concept.value;
    axios
      .get('/api/search', {params: {concept: concept}})
      .then(((response) => {
        console.log('Received search results', response.data);
        this.props.result.clips = response.data.clips;
        this.props.result.videos = response.data.videos;
      }).bind(this));
  }

  _onSelectConcept(e) {
    this.setState({selectedConcept: e.target.value});
  }

  _onSelectPropertyKey(e) {
    this.setState({selectedProperty: e.target.selectedIndex});
  }

  _onAddProperty(e) {
    console.log("adding property")
    let form = ReactDOM.findDOMNode(this._form);
    let key = form.elements['property-key'].value;
    let value = form.elements['property-value'].value;
    this.state.properties.push([`${this.state.selectedConcept}.${key}`, value]);
    this.setState({selectedProperty: null});
  }

  render() {
    let selectSize = (n) => Math.max(Math.min(n, 5), 2)
    return (
      <Form className='search-input' onSubmit={this._onSearch.bind(this)} ref={(n) => {this._form = n;}}>
        <FormGroup controlId="concept" onChange={this._onSelectConcept.bind(this)}>
          <ControlLabel>Concept:</ControlLabel>
          <FormControl componentClass="select" placeholder="Select...">
            <option value="video">Video</option>
            <option value="face">Face</option>
            <option value="face_diffs">Face Diffs</option>
          </FormControl>
        </FormGroup>
        <FormGroup controlId="active-properties">
          <ControlLabel>Constraints:</ControlLabel>
          <FormControl componentClass="select"
                       size={selectSize(this.state.properties.length)}>
            {this.state.properties.map((prop, i) =>
              <option value={i} key={i}>{`${prop[0]} = ${prop[1]}`}</option>
             )}
          </FormControl>
        </FormGroup>
        <FormGroup controlId="property-key">
          <ControlLabel>Property:</ControlLabel>
          <FormControl componentClass="select"
                       size={selectSize(this.properties[this.state.selectedConcept].length)}
                       onChange={this._onSelectPropertyKey.bind(this)}>
            {this.properties[this.state.selectedConcept].map((keys) => {
               return <option key={keys[0]} value={keys[0]}>{keys[0]}</option>;
             })}
          </FormControl>
        </FormGroup>
        {this.state.selectedProperty != null
         ? <FormGroup controlId="property-value">
           <ControlLabel>Value:</ControlLabel>
           <InputGroup>
             <PropertyInput type={this.properties[this.state.selectedConcept][this.state.selectedProperty][1]} />
             <InputGroup.Button>
               <Button onClick={this._onAddProperty.bind(this)}>Add</Button>
             </InputGroup.Button>
           </InputGroup>
         </FormGroup>
         : <div />}
        <Button type="submit">Search</Button>
      </Form>
    );
  }
}

class SearchResultView extends React.Component {
  state = {
    hover: false,
    showVideo: false,
    needsUpdate: false
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
    console.log('gotcha');
  }

  _toSeconds(frame) {
    return frame / this.props.video.fps;
  }

  // CHECK(pari): need to round down right?
  _toFrame(seconds) {
    return Math.floor(seconds * this.props.video.fps);
  }

  _onSeeked = () => {
    this.setState({showVideo: true});
  }

  _onLoadedData = () => {
    console.log(this.props.clip.start, this.props.video.fps, this.props.video.num_frames);
    this._video.currentTime = this._toSeconds(this.props.clip.start);
  }

  // FIXME: slightly hacky because set this up to fire whenever video is paused - the way we're
  // using it, it seems fine because after pause = mouse leaving video - and video restarts after.
  _onEnd = () => {
    // set _test_box state to the 0th frame.
    let curBox = this.props.clip.bboxes[0][0];
    this._test_box.setState({x1: curBox.x1, x2: curBox.x2, y1: curBox.y1, y2: curBox.y2});
  }

  // Will fire only when video time is updated.
  _onTimeUpdate = () => {
    if (this._video.currentTime >= this._toSeconds(this.props.clip.end)) {
      this._video.currentTime = this._toSeconds(this.props.clip.start);
    }
    // FIXME: these things would start failing if we were trying to display multiple faces

    /* Here, we want to update the x1,y1,x2,y2 values in the face_box based on apprx the
     time->frame conversion. */

    // Find the frame (approx) corresponding to current time
    let cur_frame = this._toFrame(this._video.currentTime);

    // FIXME: It seems we're off by one here and cur_frame is sometimes -1 of start...
    console.assert(cur_frame >= this.props.clip.start, 'cur frame lower than start');
    console.assert(cur_frame < this.props.clip.end, 'cur frame higher than end?');

    let index = Math.floor((cur_frame - this.props.clip.start) / DETECTION_FPS);
    // deal with negative frames...
    index = Math.max(0, index);
    // deal with index being too far beyond end...
    index = Math.min(index, this.props.clip.bboxes[0].length-1);
    let curBox = this.props.clip.bboxes[0][index];

    // update state of the face box
    this._test_box.setState({x1: curBox.x1, x2: curBox.x2, y1: curBox.y1, y2: curBox.y2});
  }

  componentDidUpdate() {
    if (this._video != null) {
      this._video.addEventListener('seeked', this._onSeeked);
      this._video.addEventListener('loadeddata', this._onLoadedData);
      this._video.addEventListener('timeupdate', this._onTimeUpdate);
      this._video.addEventListener('pause', this._onEnd);
    }
  }

  // FIXME: This is being reused with the BoundingBoxes class ...
  _getDimensions() {
    return {
      width: this.state.fullwidth ? 780 : (this.props.video.width * (100 / this.props.video.height)),
      height: this.state.fullwidth ? (this.props.video.height * (780 / this.props.video.width)) : 100
    };
  }

  render() {
    let vidStyle = this.state.showVideo ? {'zIndex': 2} : {};
    let {width, height} = this._getDimensions();

    let face_box = <div/>
    if (this.props.clip.bboxes.length > 0) {
      /* Generate a face tracking BoxView here if clip.bboxes are there, then embed it into the
       * search-result div.*/
      let test_box = this.props.clip.bboxes[0][0];
      // TODO: add the reference to a list as in the future there can be multiple bbox's
      face_box = <BoxView box={test_box} key={0} width={width} height={height}
          color={'blue'} ref={(n) => {this._test_box = n}}
          zIndex = {3} />
    }

    return (
      <div className='search-result'
           onMouseEnter={this._onMouseEnter.bind(this)}
           onMouseLeave={this._onMouseLeave.bind(this)}
           onClick={this._onClick}>
        {face_box}
        {this.state.hover
         ? <video autoPlay muted ref={(n) => {this._video = n;}} style={vidStyle}>
           <source src={`/fs/usr/src/app/${this.props.video.path}`} />
           {/*TODO: Make this work!*/}
           {/*<track kind="subtitles" label="English subtitles" src="test.vtt" default></track>          */}
           </video>
         : <div />}

        <BoundingBoxView
            bboxes= {this.props.clip.bboxes}
            color = {this.props.clip.color}
            width = {this.props.video.width}
            height= {this.props.video.height}
            path={`/static/thumbnails/frame_${this.props.clip.frame}.jpg`}
            zIndex={1} />
      </div>
    );
  }
}

@observer
export default class Home extends React.Component {
  constructor(props) {
    super(props);
    this._result = new SearchResult();
  }


  render() {
    let video_keys = _.keys(this._result.videos);
    video_keys.sort();

    return (
      <div className='row'>
        <div className='col-md-3'>
          <SearchInput result={this._result} />
        </div>
        <div className='search-results col-md-9'>
          {video_keys.map((key, i) =>
            <div key={i}>
              <div>{this._result.videos[key].path}</div>
              <div className='search-result-video'>
                {this._result.clips[key].map((clip, j) =>
                  <SearchResultView key={j} video={this._result.videos[key]} clip={clip} />
                 )}
              </div>
            </div>
           )}
        </div>
      </div>
    );
  }

// return <BoundingBoxView src={`/static/thumbnails/frame_${frame.frame}.jpg`} />;
};
