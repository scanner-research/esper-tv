import React from 'react';
import Measure from 'react-measure';

export default class BoundingBoxView extends React.Component {
  state = {width: -1, height: -1}

  render() {
    let {width, height} = this.state;
    return (
        <Measure bounds onResize={(r) => { this.setState(r.bounds); }}>
          {({ measureRef }) =>
            <div ref={measureRef} className='bounding-boxes'>
              <img src={this.props.path} />
            </div>
          }
        </Measure>
    );
  }
};
