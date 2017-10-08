import React from 'react';
import axios from 'axios';
import ReactDOM from 'react-dom';
import {Form, FormGroup, FormControl, FieldGroup, ControlLabel, InputGroup, Button} from 'react-bootstrap';

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

export default class SearchInput extends React.Component {
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
    selectedConcept: 'video',
    selectedProperty: null,
    selectedFilter: null,
    selectedOrderBy: null,
    selectedQueryType: 'face',
    properties: [],
    filters: [],
    orderby: [],
    searching: false,
    currFilterField: '',
    currFilterType: 'eq',
    currFilterValue: '',
    currOrderBy: ''
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

  queryTypeMap = {
      'face' : 'Face',
      'frame' : 'Frame',
      'video' : 'Video'
  }

  _onSearch(e) {
    e.preventDefault();
    let concept = e.target.concept.value;
    let filters = JSON.stringify(this.state.filters);
    let orderby = JSON.stringify(this.state.orderby);
    let querytype = this.state.selectedQueryType
    this.setState({searching: true});
    axios
      .get('/api/search', {params: {concept: concept, filters: filters, orderby: orderby, querytype: querytype}})
      .then(((response) => {
        console.log('Received search results', response.data);
        this.props.onSearch(response.data);
        this.setState({searching: false});
      }).bind(this))
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

  _onChangeOrderBy(e){
    this.setState({currOrderBy : e.target.value})
  }

  _onAddOrderBy(e){
    let orderByStr = this.state.currOrderBy.trim()
    if (orderByStr.length > 0){
      this.state.orderby.push(orderByStr);
    }
    this.setState({orderby: this.state.orderby, currOrderBy: ''})
  }

  _onSelectOrderBy(e){
    this.setState({selectedOrderBy : e.target.value});
  }

  _onRemoveOrderBy(e){
    let rem_idx = this.state.selectedOrderBy;
    if (rem_idx >= 0){
      this.state.orderby.splice(rem_idx, 1);
      this.setState({selectedOrderBy: -1});
    }
  }

  _onChangeQueryType(e){
    this.setState({selectedQueryType : e.target.value});
  }

  render() {
    let selectSize = (n) => Math.max(Math.min(n, 5), 2)
    return (
      <Form className='search-input' onSubmit={this._onSearch.bind(this)} ref={(n) => {this._form = n;}}>
        <FormGroup controlId="concept" onChange={this._onSelectConcept.bind(this)}>
          <ControlLabel>Concept:</ControlLabel>
          <FormControl componentClass="select" placeholder="Select..." defaultValue={this.state.selectedConcept}>
            <option value="video">Video</option>
            <option value="face">Face</option>
            <option value="faceinstance_diffs">Face Diffs</option>
            <option value="query">Query</option>
          </FormControl>
        </FormGroup>
        {this.state.selectedConcept == "query" ?
        <div>
        <FormGroup id="query-type">
          <ControlLabel>Query Type:</ControlLabel>
          <FormControl componentClass="select"
                       value={this.state.currQueryType}
                       onChange={this._onChangeQueryType.bind(this)}>
            {_.map(this.queryTypeMap, ( (value, key) => {
              return <option key={key} value={key}>{value}</option>;
                                                             }))}
          </FormControl>
        </FormGroup>
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
<div>
          <ControlLabel>Order By:</ControlLabel>
          <FormControl componentClass="select"
                       size={selectSize(this.state.orderby.length)}
                       value={this.state.filters.selectedOrderBy}
                       onChange={this._onSelectOrderBy.bind(this)}>
            {this.state.orderby.map((keys, i) => {
               return <option key={i} value={i}>{keys}</option>;
             })}
          </FormControl>
          <Button id='rem-orderby-button' onClick={this._onRemoveOrderBy.bind(this)}>Remove Order By</Button>
          </div>
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
          </FormControl>
          <FormControl id='filter-value'
                       type="text"
                       value={this.state.currFilterValue}
                       placeholder="Filter value"
                       onChange={this._onChangeFilterValue.bind(this)}/>
          <Button id='add-filter' onClick={this._onAddFilter.bind(this)}>Add Filter</Button>
        </FormGroup>
        <FormGroup controlId="orderby-add">
          <ControlLabel>Add Order By:</ControlLabel>
          <FormControl id='orderby-input'
                       type="text"
                       value={this.state.currOrderBy}
                       placeholder="Order By Value"
                       onChange={this._onChangeOrderBy.bind(this)}/>
          <Button id='add-orderby' onClick={this._onAddOrderBy.bind(this)}>Add Filter</Button>
        </FormGroup>
        </div>
        :
        <div>
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
          </div>}
        <Button type="submit" disabled={this.state.searching}>Search</Button>
        {this.state.searching
         ? <img className='spinner' src="/static/images/spinner.gif" />
         : <div />}
      </Form>
    );
  }
}
