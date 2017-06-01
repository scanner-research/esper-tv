import React from 'react';
import {IdentityCollection} from 'models/identity.jsx';
import {IdentitySummary} from 'views/identity_summary.jsx';
import {observer} from 'mobx-react';

import {Video} from 'models/video.jsx';
import VideoSummary from 'views/video_summary.jsx';

@observer
export default class Identities extends React.Component {
  constructor(props) {
    super(props);
    this.ids = new IdentityCollection();
  }

  render() {
    console.log("in identities render");
    return (
      // Create new div for each of the identities.
      <div>
        {this.ids.ids.map((id, index) =>
          <IdentitySummary key={index} store={id} show_meta={true} frame={0} />
         )}
      </div>
    );
  }
};
