/*
 * index.jsx - Application entrypoint
 *
 * This file is called when the page is loaded. It loads any necessary CSS files
 * and initializes the App React view.
 */

import React from 'react';
import ReactDOM from 'react-dom';
import App from './app';

import 'bootstrap/dist/css/bootstrap.min.css';
import 'css/main.scss';

ReactDOM.render(<App />, document.getElementById('app'));
