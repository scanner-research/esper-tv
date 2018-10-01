/*
 * web.jsx - Application entrypoint
 *
 * This file is called when the page is loaded. It initializes the App React view.
 */

import axios from 'axios';
import {observer} from 'mobx-react';
import React from 'react';
import ReactDOM from 'react-dom';
import SearchInput from './SearchInput.jsx';
import Sidebar from './Sidebar.jsx';
import VGrid from 'vgrid';
import {SettingsContext, DataContext} from './contexts';
import Provider from './Provider.jsx';
import Consumer from './Consumer.jsx';
import {observable} from 'mobx';

// Make AJAX work with Django's CSRF protection
// https://stackoverflow.com/questions/39254562/csrf-with-django-reactredux-using-axios
axios.defaults.xsrfHeaderName = "X-CSRFToken";

@observer
export default class App extends React.Component {
  state = {
    valid: true,
    clickedBox: null,
    dataContext: null,
  }

  constructor() {
    super();

    // Hacky way for us to publicly expose a demo while reducing remote code executixon risk.
    if (GLOBALS.bucket === 'esper') {
      let img = new Image();
      img.onerror = (() => this.setState({valid: false})).bind(this);
      img.src = "https://storage.cloud.google.com/esper/do_not_delete.jpg";
    }

    this._settings = observable.map({});
  }

  _onSearch = (results) => {
    this.setState({dataContext: results});
  }

  _onBoxClick = (box) => {
    this.setState({clickedBox: box.id});
  }

  _onSave = (toSave) => {
    return axios.post('/api/labeled', toSave);
  }

  render() {
    if (this.state.valid) {
      return (
        <div>
          <h1>Esper</h1>
          <div className='home'>
            <Provider values={[
              [DataContext, this.state.dataContext],
              [SettingsContext, this._settings]]}>
              <div>
                <SearchInput onSearch={this._onSearch} clickedBox={this.state.clickedBox} />
                {this.state.dataContext !== null
                 ? (this.state.dataContext.groups.length > 0
                  ? <div className='search-result'>
                    <VGrid data={this.state.dataContext} settings={this._settings}
                           onSave={this._onSave} />
                    <Sidebar />
                  </div>
                  : <div>No results matching query.</div>)
                 : null}
              </div>
            </Provider>
          </div>
        </div>
      );
    } else {
      return <div className='login-error'>You must be logged into a validated Google account to access Esper.</div>
    }
  }
};

ReactDOM.render(<App />, document.getElementById('app'));
