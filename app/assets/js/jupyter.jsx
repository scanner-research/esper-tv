import React from 'react';
import ReactDOM from 'react-dom';
import axios from 'axios';
import SearchResultView from 'views/SearchResultView.jsx';
import SearchResult from 'models/SearchResult.jsx';
import {PythonContext, BackendSettingsContext, SearchContext} from 'views/contexts.jsx';
import Provider from 'utils/Provider.jsx';

// For some reason, `import` syntax doesn't work here? AMD issues?
let widgets = require('@jupyter-widgets/base');

// Use window.require so webpack doesn't try to import ahead of time
let Jupyter = window.require('base/js/namespace');

export let EsperView = widgets.DOMWidgetView.extend({
  render: function() {
    let result = this.model.get('result');
    let globals = this.model.get('jsglobals');
    let settings = this.model.get('settings');
    let searchResult = new SearchResult(result);
    let fields = {
      selected: []
    };
    let updateFields = (updates) => {
      Object.assign(fields, updates);
      for (let [k, v] of Object.entries(fields)) {
        this.model.set(k, v);
      }
      console.log(this.model, fields);
      this.model.save_changes();
    };

    ReactDOM.render(
      <Provider values={[
        [PythonContext, {fields: fields, update: updateFields}],
        [BackendSettingsContext, globals],
        [SearchContext, searchResult]]}>
        <div className='esper' onClick={(e) => { e.stopPropagation(); }}>
          <SearchResultView jupyter={Jupyter} settings={settings} />
        </div>
      </Provider>,
      this.el);
  },
});

export let version = '0.1.0';
