import React from 'react';
import Video from './video.jsx';
import Home from './home.jsx';
import {BrowserRouter as Router, Route} from 'react-router-dom';

const render_component = (Component) => (
  ({ match }) => (<Component {...match.params} />)
);

export default class App extends React.Component {
  render() {
    return (
      <Router>
        <div>
          <h1>Esper</h1>
          <Route exact path="/" component={render_component(Home)} />
          <Route path="/video/:id" component={render_component(Video)} />
        </div>
      </Router>
    );
  }
};
