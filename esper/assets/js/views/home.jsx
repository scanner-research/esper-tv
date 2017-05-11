import React from 'react';
import VideoSummary from 'views/video_summary.jsx';
import {VideoCollection} from 'models/video.jsx';
import {observer} from 'mobx-react';

@observer
export default class Home extends React.Component {
  constructor(props) {
    super(props);
    this.videos = new VideoCollection();
  }

  render() {
    return (
      <div>
        {this.videos.videos.map((vid, index) => {
           return <VideoSummary key={index} store={vid} />;
         })}
      </div>
    );
  }
};
