import React from 'react';
import {observer} from 'mobx-react';

import VideoSummary from './video_summary.jsx';
import * as models from 'models/mod.jsx';
import {Button, Collapse} from 'react-bootstrap';

@observer
export default class Home extends React.Component {
  constructor(props) {
    super(props);
    this.videos = new models.VideoCollection();
  }

  render() {
    return (
      <div>
        {this.videos.videos.map((vid, index) =>
          <VideoSummary key={index} store={vid} show_meta={true} frame={0} />
         )}
      </div>
    );
  }
};
