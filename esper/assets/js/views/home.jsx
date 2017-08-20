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
};

class PropertyInput extends React.Component {
  render() {
    if (this.props.type == "string") {
      return <FormControl type="text" />;
    } else if (this.props.type == "enum") {
      return <FormControl componentClass="select"><option>TODO</option></FormControl>;
    } else if (this.props.type == "int") {
      return <FormControl type="number" />;
    } else {
      console.error(`Invalid property type ${this.props.type}`);
    }
  }
};

class SearchInput extends React.Component {
  properties = {
    video: [
      ['path', 'string'],
      ['fps', 'int']
    ],
    face: [
      ['identity', 'enum']
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
    let form = ReactDOM.findDOMNode(this._form);
    let key = form.elements['property-key'].value;
    let value = form.elements['property-value'].value;
    this.state.properties.push([key, value]);
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
          </FormControl>
        </FormGroup>
        <FormGroup controlId="active-properties">
          <ControlLabel>Properties:</ControlLabel>
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
              <div>
                {this._result.clips[key].map((clip, j) => {
                   let video = this._result.videos[key];
                   return <BoundingBoxView
                              key={j} bboxes={clip.bboxes} width={video.width}
                              height={video.height}
                              path={`/static/thumbnails/frame_${clip.frame}.jpg`}/>;
                 })}
              </div>
            </div>
           )}
        </div>
      </div>
    );
  }

// return <BoundingBoxView src={`/static/thumbnails/frame_${frame.frame}.jpg`} />;
};
