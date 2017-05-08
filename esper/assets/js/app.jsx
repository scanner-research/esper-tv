import React from 'react';
import axios from 'axios';
import Video from './video.jsx';

export default class App extends React.Component {
  constructor(props) {
    super(props);
    this.state = {videos: []};
    axios.get('/videos')
         .then(((response) => {
           let videos = response.data.videos;
           this.setState({videos: videos});
         }).bind(this));
  }

  render() {
    return (
      <div>
        <h1>Esper</h1>
        {this.state.videos.map((vid, index) => {
           return <Video key={index} {...vid} />;
        })}
      </div>
    );
  }
};
