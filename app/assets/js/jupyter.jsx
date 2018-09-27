import React from 'react';
import ReactDOM from 'react-dom';
import axios from 'axios';
import _ from 'lodash';
import Groups from 'views/Groups.jsx';
import {PythonContext, DataContext} from 'views/contexts.jsx';
import Provider from 'utils/Provider.jsx';

// For some reason, `import` syntax doesn't work here? AMD issues?
let widgets = require('@jupyter-widgets/base');

// Use window.require so webpack doesn't try to import ahead of time
let Jupyter = window.require('base/js/namespace');

export let Esper = widgets.DOMWidgetView.extend({
  render: function() {
    let data = this.model.get('result');
    let settings = this.model.get('settings');
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
        [DataContext, dataContext]]}>
        <div className='esper' onClick={(e) => { e.stopPropagation(); }}>
          <Groups jupyter={Jupyter} settings={settings} />
        </div>
      </Provider>,
      this.el);
  },
});

export let version = '0.1.0';
