/*
 * app.jsx - Central dispatcher for different pages
 *
 * The main function of the App is to use the react-router to dispatch URL
 * requests to the appropriate React View.
 */

import React from 'react';
import {BrowserRouter as Router, Route, Link} from 'react-router-dom';
import * as views from './views/mod.jsx';

const render_component = (Component) => (
  ({ match }) => (<Component {...match.params} />)
);

export default class App extends React.Component {
  render() {
    return (
      <Router>
        <div>
          <h1><Link to="/">Esper</Link></h1>
          <Route exact path="/" component={render_component(views.Home)} />
        </div>
      </Router>
    );
  }
};
