import React from 'react';
import axios from 'axios';
import ReactDOM from 'react-dom';
import brace from 'brace';
import {Form, FormGroup, FormControl, FieldGroup, ControlLabel, InputGroup, Button} from 'react-bootstrap';
import AceEditor from 'react-ace';

import 'brace/mode/python'
import 'brace/theme/github'

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
          .post('/api/schema', {cls_name: cls_name, field: field})
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
          {SCHEMA.map((cls, i) =>
            <div key={i} className='schema-class'>
              <div className='schema-class-name'>{cls[0]}</div>
              <div className='schema-class-fields'>
                {cls[1].map((field, j) =>
                  <div className='schema-field' key={j} onClick={() => this._onClick(cls[0], field)}>{field}</div>
                )}
              </div>
            </div>
          )}
        </div>
        {this.state.loadingExamples
         ? <img className='spinner' src="/static/images/spinner.gif" />
         : <div />}
        {this.state.showExamples
         ? <div className='schema-example'>
           <div className='schema-example-name'>{this.exampleField}</div>
           <div>
             {this.examples[this.exampleField]
              ? this.examples[this.exampleField].map((example, i) =>
                <div key={i}>{example}</div>
              )
              : <div>Field cannot be displayed (not serializable, likely binary data).</div>}
           </div>
         </div>
         : <div />}
      </div>
    );
  }
}

export default class SearchInputView extends React.Component {
  state = {
    searching: false,
    showSchema: false,
    showExampleQueries: false
  }

  exampleQueries = [
    ["All frames",
     "result = Frame.objects.all()"],
    ["Frames at 2 FPS",
     "result = at_fps(Frame.objects, 2)"],
    ["All faces",
     "result = FaceInstance.objects.all()"],
    ["Handlabeled faces",
     "result = FaceInstance.objects.filter(labeler__name='handlabeled')"],
    ["Faces from Fox News",
     "result = FaceInstance.objects.filter(frame__video__channel='FOXNEWS')"],
    ["All face tracks",
     "result = Face.objects.all()"],
  ]

  query = `result = Face.objects.all()`

  _onSearch = (e) => {
    e.preventDefault();
    this.setState({searching: true});
    axios
      .post('/api/search2', {code: this._editor.editor.getValue()})
      .then((response) => {
        if (response.data.success) {
          this.props.onSearch(response.data.success);
        } else {
          console.error(response.data.error);
        }
      })
      .catch((error) => {
        console.error(error);
      })
      .then(() => {
        this.setState({searching: false});
      });
  }

  /* Hacks to avoid code getting wiped out when setState causes the form to re-render. */
  _onCodeChange = (newCode) => {
    this.query = newCode;
  }
  componentDidUpdate() {
    this._editor.editor.setValue(this.query, 1);
  }

  render() {
    return (
      <Form className='search-input' onSubmit={this._onSearch} ref={(n) => {this._form = n;}}>
        <AceEditor
          mode="python"
          theme="github"
          width='auto'
          minLines={1}
          maxLines={20}
          highlightActiveLine={false}
          showGutter={false}
          showPrintMargin={false}
          onChange={this._onCodeChange}
          defaultValue={this.query}
          editorProps={{$blockScrolling: Infinity}}
          ref={(n) => {this._editor = n;}} />
        <Button type="submit" disabled={this.state.searching}>Search</Button>
        <Button onClick={() => {this.setState({showSchema: !this.state.showSchema})}}>
          {this.state.showSchema ? 'Hide' : 'Show'} Schema
        </Button>
        <Button onClick={() => {this.setState({showExampleQueries: !this.state.showExampleQueries})}}>
          {this.state.showExampleQueries ? 'Hide' : 'Show'} Example Queries
        </Button>
        {this.state.searching
         ? <img className='spinner' src="/static/images/spinner.gif" />
         : <div />}
        {this.state.showExampleQueries
         ? <div>
           {this.exampleQueries.map((q, i) => {
              return (<span key={i}><a href="#" onClick={() => {this.query = q[1]; this.forceUpdate()}}>{q[0]}</a>
              <br /></span>);
           })}
           </div>
         : <div />}
        {this.state.showSchema ? <SchemaView /> : <div />}
      </Form>
    );
  }
}
