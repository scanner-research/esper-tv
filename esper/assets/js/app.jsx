import React from 'react';
import {BrowserRouter as Router, Route, Link} from 'react-router-dom';
import Video from './views/video.jsx';
import Home from './views/home.jsx';

const render_component = (Component) => (
  ({ match }) => (<Component {...match.params} />)
);

export default class App extends React.Component {
  render() {
    return (
      <Router>
        <div>
          <h1><Link to="/">Esper</Link></h1>
          <Route exact path="/" component={render_component(Home)} />
          <Route path="/video/:id" component={render_component(Video)} />
        </div>
      </Router>
    );
  }
};
