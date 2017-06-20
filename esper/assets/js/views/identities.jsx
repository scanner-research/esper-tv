import React from 'react';
import {observer} from 'mobx-react';

import * as models from 'models/mod.jsx';
import IdentitySummary from './identity_summary.jsx';

@observer
export default class Identities extends React.Component {
  constructor(props) {
    super(props);
    this.ids = new models.IdentityCollection();
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
