import React from 'react';
import mobx from 'mobx';
import _ from 'lodash';
import leftPad from 'left-pad';
import axios from 'axios';
import {observer} from 'mobx-react';
import {Button, Collapse} from 'react-bootstrap';

import * as models from 'models/mod.jsx';
import VideoSummary from './video_summary.jsx';
import {Box, BoundingBoxView, boundingRect} from './bbox.jsx';

@observer
class VideoView extends React.Component {
  constructor(...args) {
    super(...args);
    this.state = {
      showAllFaces: false,
      frame: 0,
      labelMode: true,
      curTrack: null,
      lastTrackBox: -1,
      segStart: -1
    };
  }

  _renderVideoSummary() {
    let video = this.props.store;
    let table = [
      ['ID', video.id],
      ['Path', video.path],
      ['# frames', video.num_frames],
      ['FPS', video.fps],
      ['Resolution', `${video.width}x${video.height}`]];

    return (
      <div className="video-meta">
        <VideoSummary store={video} frame={this.state.frame} show_meta={false} />
        <h2>Metadata</h2>
        <table className="table">
          <tbody>
            {table.map((pair, i) =>
              <tr key={i}><td>{pair[0]}</td><td>{pair[1]}</td></tr>
             )}
          </tbody>
        </table>
        <Button onClick={() => this.setState({labelMode: !this.state.labelMode})}>
          {this.state.labelMode ? 'View mode' : 'Label mode'}
        </Button>
        {this.state.labelMode
         ? <div>
           <br />
           <u>Instructions</u>
           <ul>
             <li><b>Click/drag image</b> - make new box</li>
             <li><b>Click/drag box</b> - move box around</li>
             <li><b>space bar</b> - change gender</li>
             <li><b>d</b> - delete box</li>
             <li><b>t</b> - manage tracks</li>
             <li><b>a</b> - mark sequence as accepted</li>
           </ul>
           <div>Current track: {this.state.curTrack || 'none'}</div>
         </div>
        : <div />}
      </div>
    );
  }

  _renderFace(face, j) {
    return <img key={j} src={`/static/thumbnails/${face.labelset}_${face.id}.jpg`}
                className={`gender-${face.gender}`} />;
  }

  _renderFaces() {
    let video = this.props.store;
    return (
      <div className="video-faces">
        {video.loadedFaces
         ? (<div>
           <div className="cluster">
             <h3>All faces
               &nbsp;
               <Button onClick={() => this.setState({showAllFaces: !this.state.showAllFaces})}>
                 +
               </Button>
             </h3>
             <Collapse in={this.state.showAllFaces}>
               <div>
                 {_.map(video.faces, (faces, i) =>
                   <div className="frame" key={i}>
                     {faces.map(this._renderFace)}
                   </div>)}
               </div>
             </Collapse>
           </div>
           <div className="clusters">
             {_.map(video.ids, (faces, i) =>
               <div className='cluster' key={i}>
                 <h3>Cluster {i}</h3>
                 {faces.map((entry, j) => {
                    let [frame, face_index] = entry;
                    let frame_faces = video.faces[frame];
                    let face = frame_faces[face_index];
                    return this._renderFace(face, j);
                  })}
               </div>
              )}
           </div>
         </div>)
         : (<div>Loading faces...</div>)}
      </div>
    );
  }

  _onFacesLoaded(wasLoaded) {
    if (!wasLoaded) { return; }
    let video = this.props.store;
    this._faces = {};
    this._allFaces = [];
    _.forEach(video.faces, (faces, frame) => {
      this._faces[frame] = faces
        .filter((face) =>
          (face.x2 - face.x1) * (face.y2 - face.y1) > .005);
      this._allFaces = this._allFaces.concat(this._faces[frame]);
    });
    this.forceUpdate();
  }

  _onChange = (box) => {
    if (box.track == null) { return; }
    this._allFaces.forEach((other_box) => {
      if (box.track == other_box.track) {
        other_box.cls = box.cls;
      }
    });
  }

  _onTrack = (box) => {
    let i = this._allFaces.indexOf(box);
    if (i == this.state.lastTrackBox) {
      console.log('Ending track');
      this.setState({curTrack: null, lastTrackBox: -1});
    } else if (this.state.curTrack == null) {
      console.log('Creating track');
      let track = box.track;
      if (track == null) {
        box.track = 100;
        track = box.track;
      }
      this.setState({curTrack: track, lastTrackBox: i});
    } else {
      console.log('Adding to track')
      box.track = this.state.curTrack;
      this.setState({lastTrackBox: i});
    }
  }

  _onAccept = (ni) => {
    let curSeg = this.state.segStart;
    if (curSeg == -1) {
      this.setState({segStart: ni});
    } else if (curSeg == ni) {
      this.setState({segStart: -1});
    } else {
      let data = {faces: {}, video: this.props.store.id};
      let segEnd = ni;
      for (var i = this.state.segStart; i <= segEnd; ++i) {
        data.faces[i * 24] = this._faces[i * 24].map((face) => face.toJSON());
      }

      axios
        .post('/api/handlabeled', data)
        .then((_) => {

        });
    }
  }

  _renderLabeler() {
    let video = this.props.store;

    if (!video.loadedFaces || !video.loadedFrames || !this._faces) {
      return <div>Loading faces...</div>;
    }

    return (
      <div className='video-labeler'>
        {_.range(0, video.num_frames, 24).map((n, ni) => {
           let path = `/static/thumbnails/${video.id}_frame_${leftPad(n+1, 6, '0')}.jpg`;
           let faces = [];
           if (n in this._faces) {
             faces = this._faces[n];
           }
           return <BoundingBoxView
                      key={n} bboxes={faces} path={path} ni={ni}
                      selected={this.state.segStart != -1 && ni == this.state.segStart}
                      accepted={n in video.frames}
                      width={video.width} height={video.height}
                      onChange={this._onChange} onTrack={this._onTrack} onAccept={this._onAccept} />;
         })}
      </div>
    );
  }

  _updateRightCol() {
    if (this._rightCol !== undefined) {
      let r = boundingRect(this._rightCol);
      this._rightCol.style.maxHeight = `${window.innerHeight - r.top}px`;
    }
  }

  componentDidMount() {
    this._updateRightCol();
  }

  render() {
    let video = this.props.store;

    video.loadFaces().then(this._onFacesLoaded.bind(this));
    video.loadFrames();

    if (!video.loadedMeta) {
      return <div>Loading video...</div>;
    }

    this._updateRightCol();

    return (
      <div className="video">
        <div className="row">
          <div className="col-md-4">
            {this._renderVideoSummary()}
          </div>
          <div className="col-md-8 right-col" ref={(n) => {this._rightCol = n;}}>
            {this.state.labelMode ? this._renderLabeler() : this._renderFaces()}
          </div>
        </div>
      </div>
    );
  }
};

export default (props) => <VideoView store={new models.Video(props.id)} />;
