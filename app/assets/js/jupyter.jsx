import React from 'react';
import ReactDOM from 'react-dom';
import axios from 'axios';
import _ from 'lodash';
import VGrid from 'vgrid';
import {observable} from 'mobx';

// For some reason, `import` syntax doesn't work here? AMD issues?
let widgets = require('@jupyter-widgets/base');

// Use window.require so webpack doesn't try to import ahead of time
let Jupyter = window.require('base/js/namespace');

export let EsperView = widgets.DOMWidgetView.extend({
  render: function() {
    let data = this.model.get('result');
    let settings = observable.map(this.model.get('settings'));
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
      <div className='esper' onClick={(e) => { e.stopPropagation(); }}>
        {data !== null ? <VGrid data={data} jupyter={Jupyter} settings={settings} /> : <span>No results.</span>}
      </div>,
      this.el);
  },
});

export let version = '0.1.0';
