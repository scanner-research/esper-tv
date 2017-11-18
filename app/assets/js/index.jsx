/*
 * index.jsx - Application entrypoint
 *
 * This file is called when the page is loaded. It loads any necessary CSS files
 * and initializes the App React view.
 */

import React from 'react';
import ReactDOM from 'react-dom';
import App from './app';
import axios from 'axios';

// Make AJAX work with Django's CSRF protection
// https://stackoverflow.com/questions/39254562/csrf-with-django-reactredux-using-axios
axios.defaults.xsrfHeaderName = "X-CSRFToken";

ReactDOM.render(<App />, document.getElementById('app'));
