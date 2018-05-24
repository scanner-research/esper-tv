/*
 * web.jsx - Application entrypoint
 *
 * This file is called when the page is loaded. It initializes the App React view.
 */

import React from 'react';
import ReactDOM from 'react-dom';
import {observable} from 'mobx';
import {observer} from 'mobx-react';
import _ from 'lodash';
import SearchResult from 'models/SearchResult.jsx';
import SearchInputView from 'views/SearchInputView.jsx';
import SearchResultView from 'views/SearchResultView.jsx';
import axios from 'axios';
import Provider from 'utils/Provider.jsx';
import {BackendSettingsContext, SearchContext} from 'views/contexts.jsx';

// Make AJAX work with Django's CSRF protection
// https://stackoverflow.com/questions/39254562/csrf-with-django-reactredux-using-axios
axios.defaults.xsrfHeaderName = "X-CSRFToken";

@observer
export default class App extends React.Component {
  state = {
    valid: true,
    clickedBox: null,
    searchResult: null,
  }

  constructor() {
    super();

    // Hacky way for us to publicly expose a demo while reducing remote code execution risk.
    if (GLOBALS.bucket === 'esper') {
      let img = new Image();
      img.onerror = (() => this.setState({valid: false})).bind(this);
      img.src = "https://storage.cloud.google.com/esper/do_not_delete.jpg";
    }
  }

  _onSearch = (results) => {
    this.setState({searchResult: new SearchResult(results)})
  }

  _onBoxClick = (box) => {
    this.setState({clickedBox: box.id});
  }

  render() {
    if (this.state.valid) {
      return (
        <div>
          <h1>Esper</h1>
          <div className='home'>
            <Provider values={[
              [BackendSettingsContext, GLOBALS],
              [SearchContext, this.state.searchResult]]}>
              <SearchInputView onSearch={this._onSearch} clickedBox={this.state.clickedBox} />
              {this.state.searchResult !== null
               ? (this.state.searchResult.result.length > 0
                ? <SearchResultView jupyter={null} settings={{}} />
                : <div>No results matching query.</div>)
               : <div />}
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
