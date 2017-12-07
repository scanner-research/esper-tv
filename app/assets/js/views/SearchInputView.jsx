import React from 'react';
import axios from 'axios';
import ReactDOM from 'react-dom';
import brace from 'brace';
import * as Rb from 'react-bootstrap';
import AceEditor from 'react-ace';
import {observer} from 'mobx-react';

import 'brace/mode/python'
import 'brace/theme/github'

@observer
class SchemaView extends React.Component {
  state = {
    loadingExamples: false,
    showExamples: false
  }

  examples = {}
  exampleField = ""

  _onClick = (cls_name, field) => {
    let full_name = cls_name + '.' + field;
    if (full_name == this.exampleField) {
      this.exampleField = '';
      this.setState({showExamples: false});
    } else {
      this.exampleField = full_name;
      if (this.examples.hasOwnProperty(full_name)) {
        this.setState({showExamples: true});
      } else {
        this.setState({showExamples: false, loadingExamples: true});
        axios
          .post('/api/schema', {dataset: DATASET, cls_name: cls_name, field: field})
          .then(((response) => {
            if (response.data.hasOwnProperty('error')) {
              this.examples[full_name] = false;
            } else {
              this.examples[full_name] = response.data['result'];
            }
            this.setState({showExamples: true});
          }).bind(this))
          .catch((error) => console.error(error))
          .then((() => {
            this.setState({loadingExamples: false});
          }));
      }
    }
  }

  render() {
    return (
      <div className='schema'>
        <div className='schema-classes'>
          {_.find(GLOBALS.schemas, (l) => l[0] == DATASET)[1].map((cls, i) =>
            <Rb.Panel key={i} className='schema-class'>
              <div className='schema-class-name'>{cls[0]}</div>
              <div className='schema-class-fields'>
                {cls[1].map((field, j) =>
                  <div className='schema-field' key={j} onClick={() => this._onClick(cls[0], field)}>{field}</div>
                )}
              </div>
            </Rb.Panel>
          )}
        </div>
        {this.state.loadingExamples
         ? <img className='spinner' />
         : <div />}
        {this.state.showExamples
         ? <Rb.Panel className='schema-example'>
           <div className='schema-example-name'>{this.exampleField}</div>
           <div>
             {this.examples[this.exampleField]
              ? this.examples[this.exampleField].map((example, i) =>
                <div key={i}>{example}</div>
              )
              : <div>Field cannot be displayed (not serializable, likely binary data).</div>}
           </div>
         </Rb.Panel>
         : <div />}
      </div>
    );
  }
}

@observer
export default class SearchInputView extends React.Component {
  state = {
    searching: false,
    showSchema: false,
    showExampleQueries: false,
    error: null
  }

  query = localStorage.getItem("lastQuery")

  _onSearch = (e) => {
    e.preventDefault();
    this.setState({searching: true, error: null});
    axios
      .post('/api/search2', {dataset: DATASET, code: this._editor.editor.getValue()})
      .then((response) => {
        if (response.data.success) {
          this.props.onSearch(response.data.success);
        } else {
          this.setState({error: response.data.error});
        }
      })
      .catch((error) => {
        this.setState({error: error});
      })
      .then(() => {
        this.setState({searching: false});
      });
  }

  _onChangeDataset = (e) => {
    DATASET.set(e.target.value);
  }

  /* Hacks to avoid code getting wiped out when setState causes the form to re-render. */
  _onCodeChange = (newCode) => {
    this.query = newCode;
    localStorage.lastQuery = this.query;
  }
  componentDidUpdate() {
    this._editor.editor.setValue(this.query, 1);
  }

  render() {
    let exampleQueries = GLOBALS.queries[DATASET];
    if (this.query === null) {
      this.query = exampleQueries[0][1];
    }

    return (
      <Rb.Form className='search-input' onSubmit={this._onSearch} ref={(n) => {this._form = n;}} inline>
        <AceEditor
          mode="python"
          theme="github"
          width='auto'
          minLines={1}
          maxLines={20}
          highlightActiveLine={false}
          showPrintMargin={false}
          onChange={this._onCodeChange}
          defaultValue={this.query}
          editorProps={{$blockScrolling: Infinity}}
          ref={(n) => {this._editor = n;}} />
        <Rb.Button type="submit" disabled={this.state.searching}>Search</Rb.Button>
        <Rb.Button onClick={() => {this.setState({showSchema: !this.state.showSchema})}} active={this.state.showSchema}>
          {this.state.showSchema ? 'Hide' : 'Show'} schema
        </Rb.Button>
        <Rb.Button onClick={() => {this.setState({showExampleQueries: !this.state.showExampleQueries})}} active={this.state.showExampleQueries}>
          {this.state.showExampleQueries ? 'Hide' : 'Show'} example queries
        </Rb.Button>
        <Rb.FormGroup>
          <Rb.ControlLabel>Dataset:</Rb.ControlLabel>
          <Rb.FormControl componentClass="select" onChange={this._onChangeDataset} defaultValue={DATASET}>
            {GLOBALS.schemas.map((l, i) =>
              <option key={i} value={l[0]}>{l[0]}</option>
            )}
          </Rb.FormControl>
        </Rb.FormGroup>
        {this.state.searching
         ? <img className='spinner' />
         : <div />}
        {this.state.showExampleQueries
         ? <Rb.Panel className='example-queries'>
           <strong>Example queries</strong><br />
           {exampleQueries.map((q, i) => {
              return (<span key={i}>
                <a href="#" onClick={(e) => {
                    e.preventDefault();
                    this.query = q[1];
                    this.forceUpdate();
                }}>{q[0]}</a>
                <br />
              </span>);
           })}
           </Rb.Panel>
         : <div />}
        {this.state.showSchema ? <SchemaView /> : <div />}
        {this.state.error !== null
        ? <Rb.Alert bsStyle="danger">
          <pre>{this.state.error}</pre>
        </Rb.Alert>
         : <div />}
      </Rb.Form>
    );
  }
}
