import React from 'react';
import ReactDOM from 'react-dom';
import {observable} from 'mobx';
import {observer} from 'mobx-react';
import axios from 'axios';
import {Box, BoundingBoxView} from './bbox.jsx';
import {Form, FormGroup, FormControl, FieldGroup, ControlLabel, InputGroup, Button} from 'react-bootstrap';

class SearchResult {
  @observable clips = {};
  @observable videos = {};
  @observable colors = {};
};

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
    face_ordered: [
      ['id', 'int'],
      ['identity', 'enum']
    ],
    faceinstance_diffs: [
      ['id', 'int']
    ],
    query: [
    ]
  }



  state = {
    selectedConcept: 'query',
    selectedProperty: null,
    selectedFilter: null,
    properties: [],
    filters: [['width', 'gte', '.1']],
    searching: false,
    currFilterField: '',
    currFilterType: 'eq',
    currFilterValue: '',
  }

  filterTypeMap = {
      'like': 'LIKE',
      'nlike': 'NOT LIKE',
      'eq': '=',
      'neq': '!=',
      'gt': '>',
      'gte': '>=',
      'lt': '<',
      'lte': '<='
  }

  _onSearch(e) {
    e.preventDefault();
    let concept = e.target.concept.value;
    let filters = JSON.stringify(this.state.filters);
    this.setState({searching: true});
    axios
      .get('/api/search', {params: {concept: concept, filters: filters}})
      .then(((response) => {
        console.log('Received search results', response.data);
        this.props.result.videos = response.data.videos;
        this.props.result.clips = response.data.clips;
        this.props.result.colors = response.data.colors;
        this.setState({searching: false});
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

  _onSelectFilter(e){
    this.setState({selectedFilter: e.target.value});
  }
  
  _onRemoveFilter(e){
    let rem_idx = this.state.selectedFilter;
    if (rem_idx >= 0){
      this.state.filters.splice(rem_idx, 1);
      this.setState({selectedFilter: -1});
    }
  } 


  _onChangeFilterField(e){
    this.setState({currFilterField: e.target.value});
  }

  _onChangeFilterType(e){
    this.setState({currFilterType: e.target.value});
  }

  _onChangeFilterValue(e){
    this.setState({currFilterValue: e.target.value});
  }

  _onAddFilter(e){
    if(this.state.currFilterField.trim().length > 0 && this.state.currFilterValue.trim().length > 0){
    this.state.filters.push([this.state.currFilterField.trim(), this.state.currFilterType, this.state.currFilterValue.trim()])
    }
    this.setState({currFilterValue: '', currFilterType: 'eq', currFilterField:''});
  }

  render() {
    let selectSize = (n) => Math.max(Math.min(n, 5), 2)
    return (
      <Form className='search-input' onSubmit={this._onSearch.bind(this)} ref={(n) => {this._form = n;}}>
        <FormGroup controlId="concept" onChange={this._onSelectConcept.bind(this)}>
          <ControlLabel>Concept:</ControlLabel>
          <FormControl componentClass="select" placeholder="Select..." value={this.state.selectedConcept}>
            <option value="video">Video</option>
            <option value="face">Face</option>
            <option value="face_ordered">Face Order</option>
            <option value="faceinstance_diffs">Face Diffs</option>
            <option value="query">Query</option>
          </FormControl>
        </FormGroup>
        {/*
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
        */}
        <FormGroup id="filter-key">
          <ControlLabel>Filters:</ControlLabel>
          <FormControl componentClass="select"
                       size={selectSize(this.state.filters.length)}
                       value={this.state.filters.selectedFilter}
                       onChange={this._onSelectFilter.bind(this)}>
            {this.state.filters.map((keys, i) => {
               return <option key={i} value={i}>{keys[0]+' '+this.filterTypeMap[keys[1]]+' '+keys[2]}</option>;
             })}
          </FormControl>
          <Button id='rem-filter-button' onClick={this._onRemoveFilter.bind(this)}>Remove Filter</Button>
        </FormGroup>
        <FormGroup id="add-filter">
          <ControlLabel>Add Filter:</ControlLabel>
          <FormControl id='filter-field'
                       type="text"
                       value={this.state.currFilterField}
                       placeholder="Filter field"
                       onChange={this._onChangeFilterField.bind(this)} />
                       
          <FormControl id="filter-type"
                       componentClass="select"
                       value={this.state.currFilterType}
                       onChange={this._onChangeFilterType.bind(this)}>
            {_.map(this.filterTypeMap, (value, key) => {
                    return <option key={key} value={key}>{value}</option>;})}
                       {/*
            <option key='eq' value='eq'>{'='}</option>
            <option key='neq' value='neq'>{'!='}</option>
            <option key='gt' value='gt'>{'>'}</option>
            <option key='gte' value='gte'>{'>='}</option>
            <option key='lt' value='lt'>{'<'}</option>
            <option key='lte' value='lte'>{'<='}</option>
            <option key='like' value='like'>{'LIKE'}</option>
            <option key='nlike' value='nlike'>{'NOT LIKE'}</option>
            */}
          </FormControl> 
          <FormControl id='filter-value'
                       type="text"
                       value={this.state.currFilterValue}
                       placeholder="Filter value"
                       onChange={this._onChangeFilterValue.bind(this)}/>
          <Button id='add-filter' onClick={this._onAddFilter.bind(this)}>Add Filter</Button>
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
        <Button type="submit" disabled={this.state.searching}>Search</Button>
        {this.state.searching
         ? <img className='spinner' src="/static/images/spinner.gif" />
         : <div />}
      </Form>
    );
  }
}

class SearchResultView extends React.Component {
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
    console.log('gotcha');
  }

  _toSeconds(frame) {
    return frame / this.props.video.fps;
  }

  _onSeeked = () => {
    this.setState({showVideo: true});
  }

  _onLoadedData = () => {
    console.log(this.props.clip.start, this.props.video.fps, this.props.video.num_frames);
    this._video.currentTime = this._toSeconds(this.props.clip.start);
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
                     color={this.props.clip.color}
                     path={path} />;
    let other_box = this.props.clip.other_bboxes
                  ? <BoundingBoxView
                        bboxes={this.props.clip.other_bboxes}
                        width={this.props.video.width}
                        height={this.props.video.height}
                        color={this.props.clip.other_color}
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
        {this.props.clip.color == "red"
         ? <div>{my_box}{other_box}</div>
         : <div>{other_box}{my_box}</div>}
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
    let orderby_keys = _.keys(this._result.clips);
    orderby_keys.sort();

    return (
      <div className='row'>
        <div className='col-md-3'>
          <SearchInput result={this._result} />
        </div>
        <div className='search-results col-md-9'>
          <div className='colors'>
            {_.keys(this._result.colors).map((name, i) =>
              <div key={i}>{name}: <div style={{backgroundColor: this._result.colors[name], width: '10px', height: '10px', display: 'inline-box'}} /></div>
            )}
          </div>
          {orderby_keys.map((key, i) =>
            <div className='search-result-video' key={i}>
              <div>{key}</div>
              <div>
                {this._result.clips[key].map((clip, j) =>
                  <SearchResultView key={j} video={this._result.videos[clip.video_id]} clip={clip} />
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
