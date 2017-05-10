import React from 'react';
import axios from 'axios';
import VideoSummary from './video_summary.jsx';

export default class App extends React.Component {
  constructor(props) {
    super(props);
    this.state = {videos: []};
    axios.get('/api/videos/')
         .then(((response) => {
           let videos = response.data.videos;
           this.setState({videos: videos});
         }).bind(this));
  }

  render() {
    return (
      <div>
        {this.state.videos.map((vid, index) => {
           return <VideoSummary key={index} {...vid} />;
         })}
      </div>
    );
  }
};
